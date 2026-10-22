"""Freeze explicit declaring types/signatures without changing the 41 target IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import javalang
from src.utils.focal_target import select_method, parameter_types
from scripts.analyze_focal_method_coverage import find_method_ranges, find_owned_method_ranges


def freeze(source_manifest: Path, projects_root: Path, owner_overrides: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    source_rows = json.loads(source_manifest.read_text(encoding="utf-8"))
    if len(source_rows) != 41 or len({row["id"] for row in source_rows}) != 41:
        raise ValueError("Expected the fixed 41 unique focal targets")
    rows, evidence = [], []
    for row in source_rows:
        target = projects_root / row["project_id"] / row["target_relative"]
        text = target.read_text(encoding="utf-8")
        tree = javalang.parse.parse(text)
        owner = (owner_overrides or {}).get(row["id"], row["fqcn"])
        _, method = select_method(tree, row["method"], owner)
        types = parameter_types(method)
        ranges = find_owned_method_ranges(text, row["method"], owner, types)
        source_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        rows.append({**row, "fqcn": owner, "method_owner": owner, "method_parameter_types": types,
                     "source_sha256": source_hash, "focal_selection_schema": "owner-signature-v1"})
        evidence.append({"id": row["id"], "owner": owner, "legacy_fqcn": row["fqcn"], "parameter_types": types,
                         "legacy_ranges": [vars(r) for r in find_method_ranges(text, row["method"])],
                         "strict_ranges": [vars(r) for r in ranges], "source_sha256": source_hash})
    return rows, {
        "method_count": len(rows), "unique_ids": len({r["id"] for r in rows}),
        "source_manifest_sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        "selection_schema": "owner-signature-v1", "targets": evidence,
        "note": "Same focal IDs and source versions; explicit owners exclude unrelated nested methods. Historical results are unchanged.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--owner-override", action="append", default=[], metavar="ID=FQCN",
                        help="Explicit evidence-backed owner correction; use $ for JVM nested-class names")
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise FileExistsError("Use new output paths; frozen manifests are not overwritten")
    overrides = {}
    for value in args.owner_override:
        if "=" not in value:
            parser.error("Owner overrides must be ID=FQCN")
        target_id, owner = value.split("=", 1)
        overrides[target_id] = owner
    source_ids = {row["id"] for row in json.loads(args.source.read_text(encoding="utf-8"))}
    if overrides.keys() - source_ids:
        parser.error("Owner override references an unknown target ID")
    rows, report = freeze(args.source, args.projects_root, overrides)
    for path, value in [(args.output, rows), (args.report, report)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"methods": len(rows), "selection_schema": report["selection_schema"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
