"""Compare paired English and Vietnamese queries on the existing pgvector index."""
import json
import os

import psycopg
from dotenv import load_dotenv

from .embeddings import OpenAIEmbedder
from .evaluation import evaluate_query, summarize
from .run import ROOT, STARTER, STRATEGIES, write_json
from .store import PgVectorStore


def main() -> None:
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL in the environment or starter/.env.")

    benchmark = ROOT / "benchmark"
    questions = json.loads((benchmark / "questions.json").read_text(encoding="utf-8"))
    translations = json.loads((benchmark / "questions_vi.json").read_text(encoding="utf-8"))
    question_ids = {question["id"] for question in questions}
    if len(question_ids) != len(questions) or translations.keys() != question_ids:
        raise SystemExit("Expected exactly one Vietnamese translation per English question ID.")

    embedder = OpenAIEmbedder()
    store = PgVectorStore(database_url, embedder.dimensions)
    traces_by_language = {}
    input_tokens = {}
    try:
        for language in ("en", "vi"):
            localized = [
                {**question, "question": translations[question["id"]]}
                if language == "vi" else question
                for question in questions
            ]
            start_tokens = embedder.input_tokens
            vectors = embedder.embed_documents([question["question"] for question in localized])
            input_tokens[language] = embedder.input_tokens - start_tokens
            traces = []
            for question, vector in zip(localized, vectors, strict=True):
                for strategy, index in STRATEGIES.items():
                    filters = question.get("filter") if strategy == "C" else None
                    hits = store.search(index, vector, top_k=3, filters=filters)
                    if len(hits) != 3:
                        raise RuntimeError(f"Expected three hits for {strategy}/{question['id']}. Run ingestion first.")
                    traces.append({
                        **evaluate_query(question, hits),
                        "language": language,
                        "strategy": strategy,
                        "applied_filter": filters,
                    })
            traces_by_language[language] = traces
    except psycopg.Error as error:
        raise SystemExit(
            f"pgvector operation failed ({error.sqlstate or type(error).__name__}). Run ingestion first."
        ) from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None

    pairs = []
    for english, vietnamese in zip(*traces_by_language.values(), strict=True):
        pairs.append({
            "id": english["id"], "split": english["split"], "strategy": english["strategy"],
            "en_hit_at_1": english["hit_at_1"], "vi_hit_at_1": vietnamese["hit_at_1"],
            "en_evidence_hit_at_3": english["evidence_hit_at_3"],
            "vi_evidence_hit_at_3": vietnamese["evidence_hit_at_3"],
        })
    output = ROOT / "results" / "language_comparison"
    output.mkdir(parents=True, exist_ok=True)
    for language, traces in traces_by_language.items():
        write_json(output / f"{language}_traces.json", traces)
    write_json(output / "paired_outcomes.json", pairs)
    metrics = {language: summarize(traces) for language, traces in traces_by_language.items()}
    write_json(output / "summary.json", {
        "model": embedder.model_name, "dimensions": embedder.dimensions,
        "query_input_tokens": input_tokens, "metrics": metrics,
    })
    for language, strategies in metrics.items():
        for strategy, splits in strategies.items():
            for split, scores in splits.items():
                count = scores["questions"]
                print(f"{language} {strategy} {split}: Hit@1 {scores['hit_at_1']}/{count}, "
                      f"Evidence Hit@3 {scores['evidence_hit_at_3']}/{count}")


if __name__ == "__main__":
    main()
