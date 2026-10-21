"""Create a route-neutral, runner-compatible fixed method list for KCF-UTG."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


RUNNER_FIELDS = (
    "id",
    "target",
    "method",
    "class_name",
    "package",
    "fqcn",
    "project_id",
    "project_name",
    "project_version",
    "java",
    "target_relative",
    "source_root",
    "source_root_relative",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(source: Path, expected_methods: int = 41, expected_projects: int = 6) -> tuple[list[dict], dict]:
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Source method list must be a JSON array")
    ids = [row.get("id") for row in rows]
    if len(rows) != expected_methods or len(set(ids)) != expected_methods:
        raise ValueError(f"Expected {expected_methods} unique methods; got {len(rows)} rows and {len(set(ids))} unique ids")
    projects = Counter(row.get("project_id", "") for row in rows)
    if len(projects) != expected_projects or "" in projects:
        raise ValueError(f"Expected {expected_projects} named projects; got {dict(projects)}")

    methods = []
    for index, row in enumerate(rows):
        missing = [field for field in RUNNER_FIELDS if field not in row]
        if missing:
            raise ValueError(f"Method row #{index} is missing runner fields: {missing}")
        methods.append({field: row[field] for field in RUNNER_FIELDS})

    card = {
        "dataset_id": "six_project_high_dependency_41_v1",
        "paper_route": "KCF-UTG RQ1/RQ2",
        "method_count": len(methods),
        "project_counts": dict(sorted(projects.items())),
        "source_manifest": str(source),
        "source_manifest_sha256": sha256(source),
        "selection_note": "Derived from the archived six-project method list; DCCI/MDCI scores are omitted from the runner manifest and are not paper metrics.",
    }
    return methods, card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-card", type=Path, required=True)
    args = parser.parse_args()

    methods, card = prepare(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.dataset_card.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(methods, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.dataset_card.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"methods": len(methods), "projects": card["project_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
