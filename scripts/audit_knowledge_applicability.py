"""Audit preserved retrieval records without calling an LLM or running tests."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.applicability import assess_record
from src.retrieval.dependency_knowledge import load_knowledge_records


def read_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("summary JSON must contain an array")
    return data


def iter_retrievals(rows: list[dict[str, Any]]):
    for row in rows:
        sources = row.get("retrieval_sources") or {}
        for phase in ("coverage-gap", "failure-repair"):
            values = sources.get(phase) or []
            if phase == "failure-repair":
                values = [record for batch in values for record in (batch.get("records") or [])]
            for record in values:
                yield row, phase, record


def audit(rows: list[dict[str, Any]], **kwargs) -> list[dict[str, Any]]:
    results = []
    for row, phase, record in iter_retrievals(rows):
        assessment = assess_record(
            record,
            target_project=str(row.get("project_id", "")),
            target_class=str(row.get("fqcn", "")),
            target_method=str(row.get("method", "")),
            **kwargs,
        )
        results.append(
            {
                "row_id": row.get("id"),
                "round": row.get("round"),
                "phase": phase,
                "record_id": record.get("id"),
                "record_project": record.get("project"),
                **assessment,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, default=Path("experiments/knowledge/dependency_construction_knowledge.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-framework", default="junit4")
    parser.add_argument("--max-java-source", type=int, default=8)
    args = parser.parse_args()

    rows = read_rows(args.summary)
    # Loading validates the knowledge file used by the experiment, even though
    # the audit uses the records embedded in the preserved run summary.
    load_knowledge_records(args.knowledge)
    results = audit(rows, target_framework=args.target_framework, max_java_source=args.max_java_source)
    counts = Counter(result["status"] for result in results)
    output = {
        "summary": {
            "rows": len(rows),
            "retrieval_records": len(results),
            "status_counts": dict(sorted(counts.items())),
        },
        "records": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
