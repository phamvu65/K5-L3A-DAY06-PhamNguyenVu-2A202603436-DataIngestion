"""Evaluate retrieval against documented evidence."""
from typing import Any


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Mark a hit when a chunk contains the full quote at a documented location."""
    gold = [question, *question.get("alternative_evidence", [])]
    ranked = []
    for rank, hit in enumerate(hits[:3], 1):
        text = " ".join(hit["text"].split())
        evidence_hit = any(
            hit["document_id"] == item["gold_source_id"]
            and hit["page"] == item["gold_page"]
            and " ".join(item["evidence_quote"].split()) in text
            for item in gold
        )
        ranked.append({**hit, "rank": rank, "evidence_hit": evidence_hit})
    filters = question.get("filter", {})
    return {
        **question,
        "hits": ranked,
        "hit_at_1": bool(ranked and ranked[0]["evidence_hit"]),
        "evidence_hit_at_3": any(hit["evidence_hit"] for hit in ranked),
        "filter_compliant": (
            bool(ranked) and all(
                all(hit["metadata"].get(key) == value for key, value in filters.items())
                for hit in ranked
            )
        ) if filters else None,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Return numerators and denominators by strategy and split."""
    groups = {}
    for trace in traces:
        group = groups.setdefault(trace["strategy"], {}).setdefault(trace["split"], {
            "questions": 0, "hit_at_1": 0, "evidence_hit_at_3": 0,
            "filter_questions": 0, "filter_compliant": 0,
        })
        group["questions"] += 1
        group["hit_at_1"] += trace["hit_at_1"]
        group["evidence_hit_at_3"] += trace["evidence_hit_at_3"]
        if trace["filter_compliant"] is not None:
            group["filter_questions"] += 1
            group["filter_compliant"] += trace["filter_compliant"]
    return groups
