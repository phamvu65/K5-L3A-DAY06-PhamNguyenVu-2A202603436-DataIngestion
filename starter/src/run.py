"""Ingest the corpus and benchmark three retrieval strategies."""
import argparse
import json
import logging
import os
from pathlib import Path
from statistics import mean
from time import perf_counter

import psycopg
from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import OpenAIEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus
from .store import PgVectorStore

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
STRATEGIES = {"A": "A", "B": "B", "C": "B"}
SELECTION_RULE = "Maximize dev Evidence Hit@3, then dev Hit@1, then prefer A, B, C in that order."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-only", action="store_true", help="Stop after selecting on dev.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.exit(1, "Set DATABASE_URL in the environment or starter/.env.\n")
    try:
        run(database_url, args.output_dir, args.dev_only)
    except psycopg.Error as error:
        parser.exit(1, f"pgvector operation failed ({error.sqlstate or type(error).__name__}).\n")
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


def run(database_url: str, output_dir: Path, dev_only: bool) -> None:
    started = perf_counter()
    pages = load_corpus(ROOT / "data" / "manifest.json")
    questions = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    if len(pages) < 30:
        raise ValueError("The corpus must contain at least 30 content pages.")
    if any(sum(q["split"] == split for q in questions) < count
           for split, count in {"dev": 15, "test": 5}.items()):
        raise ValueError("The benchmark requires at least 15 dev and 5 test questions.")
    print(f"Loaded {len(pages)} content pages. {SELECTION_RULE}", flush=True)

    embedder = OpenAIEmbedder()
    store = PgVectorStore(database_url, embedder.dimensions)
    store.create_schema()
    chunks_by_strategy = {
        "A": [chunk for page in pages for chunk in fixed_size(page, 500, 50)],
        "B": [chunk for page in pages for chunk in by_paragraph(page, 500)],
    }
    stats = {}
    for strategy, chunks in chunks_by_strategy.items():
        strategy_started = perf_counter()
        previous_tokens = embedder.input_tokens
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        store.upsert(strategy, chunks, vectors)
        lengths = [len(chunk.text) for chunk in chunks]
        stats[strategy] = {
            "chunks": len(chunks),
            "characters": sum(lengths),
            "min_characters": min(lengths),
            "max_characters": max(lengths),
            "mean_characters": round(mean(lengths), 2),
            "input_tokens": embedder.input_tokens - previous_tokens,
            "embed_and_store_seconds": round(perf_counter() - strategy_started, 3),
        }
        print(f"Ingested {strategy}: {len(chunks)} chunks.", flush=True)
    stats["C"] = {"reuses": "B", "chunks": stats["B"]["chunks"]}
    ingest_seconds = round(perf_counter() - started, 3)

    traces = []
    query_tokens = {}
    for split in ("dev",) if dev_only else ("dev", "test"):
        selected_questions = [q for q in questions if q["split"] == split]
        previous_tokens = embedder.input_tokens
        query_vectors = embedder.embed_documents([q["question"] for q in selected_questions])
        query_tokens[split] = embedder.input_tokens - previous_tokens
        split_traces = []
        for question, vector in zip(selected_questions, query_vectors, strict=True):
            for strategy, index in STRATEGIES.items():
                filters = question.get("filter") if strategy == "C" else None
                hits = store.search(index, vector, top_k=3, filters=filters)
                trace = evaluate_query(question, hits)
                split_traces.append({**trace, "strategy": strategy, "applied_filter": filters})
        write_json(output_dir / f"{split}_traces.json", split_traces)
        traces.extend(split_traces)
        metrics = summarize(traces)
        if split == "dev":
            chosen = max(STRATEGIES, key=lambda strategy: (
                metrics[strategy]["dev"]["evidence_hit_at_3"],
                metrics[strategy]["dev"]["hit_at_1"],
            ))
            write_json(output_dir / "selection.json", {"rule": SELECTION_RULE, "strategy": chosen})
            print(f"Selected on dev: {chosen}.", flush=True)
        write_json(output_dir / "summary.json", {
            "model": embedder.model_name,
            "dimensions": embedder.dimensions,
            "search": "exact cosine",
            "ingest_seconds": ingest_seconds,
            "strategies": stats,
            "query_input_tokens": query_tokens,
            "total_input_tokens": embedder.input_tokens,
            "selected_strategy": chosen,
            "metrics": metrics,
        })
        for strategy in STRATEGIES:
            row = metrics[strategy][split]
            print(f"{split} {strategy}: Hit@1 {row['hit_at_1']}/{row['questions']}, "
                  f"Evidence Hit@3 {row['evidence_hit_at_3']}/{row['questions']}", flush=True)


def write_json(path: Path, data: dict | list) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    main()
