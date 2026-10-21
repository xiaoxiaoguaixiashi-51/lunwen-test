"""Recompute a coverage summary on a fixed focal-method denominator."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_detail(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No detail rows in {path}")
    indexed = {row["id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate focal method ids in {path}")
    return indexed


def normalize(
    reference: dict[str, dict[str, str]],
    candidate: dict[str, dict[str, str]],
    reference_prefix: str,
    candidate_prefix: str,
) -> dict[str, Any]:
    if reference.keys() != candidate.keys():
        missing = sorted(reference.keys() - candidate.keys())
        extra = sorted(candidate.keys() - reference.keys())
        raise ValueError(f"Method list mismatch: missing={missing}, extra={extra}")

    methods = []
    totals = {"lines_total": 0, "lines_covered": 0, "branches_total": 0, "branches_covered": 0}
    missing_coverage = []
    for method_id, ref in reference.items():
        row = candidate[method_id]
        for key in ("target", "method", "line_ranges"):
            if ref.get(key) != row.get(key):
                raise ValueError(f"Method metadata mismatch for {method_id}: {key}")

        ref_lines_total = int(ref.get(f"{reference_prefix}_lines_total") or 0)
        ref_branches_total = int(ref.get(f"{reference_prefix}_branches_total") or 0)
        candidate_line_rate = row.get(f"{candidate_prefix}_line_rate", "")
        candidate_branch_rate = row.get(f"{candidate_prefix}_branch_rate", "")
        has_coverage = bool(candidate_line_rate or candidate_branch_rate)

        lines_total = int(row.get(f"{candidate_prefix}_lines_total") or 0) if has_coverage else ref_lines_total
        branches_total = int(row.get(f"{candidate_prefix}_branches_total") or 0) if has_coverage else ref_branches_total
        if has_coverage and (lines_total != ref_lines_total or branches_total != ref_branches_total):
            raise ValueError(
                f"Coverage denominator mismatch for {method_id}: "
                f"candidate=({lines_total},{branches_total}) reference=({ref_lines_total},{ref_branches_total})"
            )

        lines_covered = int(row.get(f"{candidate_prefix}_lines_covered") or 0)
        branches_covered = int(row.get(f"{candidate_prefix}_branches_covered") or 0)
        if not has_coverage:
            missing_coverage.append(method_id)
        item = {
            "id": method_id,
            "target": row.get("target", ""),
            "method": row.get("method", ""),
            "line_ranges": row.get("line_ranges", ""),
            "coverage_present": has_coverage,
            "lines_total": lines_total,
            "lines_covered": lines_covered,
            "branches_total": branches_total,
            "branches_covered": branches_covered,
        }
        methods.append(item)
        for key in totals:
            totals[key] += item[key]

    return {
        "methods_total": len(methods),
        "methods_with_coverage_data": len(methods) - len(missing_coverage),
        "methods_missing_coverage": missing_coverage,
        **totals,
        "line_rate": totals["lines_covered"] / totals["lines_total"] if totals["lines_total"] else 0.0,
        "branch_rate": totals["branches_covered"] / totals["branches_total"] if totals["branches_total"] else 0.0,
        "methods": methods,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-detail", type=Path, required=True)
    parser.add_argument("--candidate-detail", type=Path, required=True)
    parser.add_argument("--reference-prefix", required=True)
    parser.add_argument("--candidate-prefix", required=True)
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = normalize(
        read_detail(args.reference_detail),
        read_detail(args.candidate_detail),
        args.reference_prefix,
        args.candidate_prefix,
    )
    output = {
        "approach": args.candidate_name,
        "denominator_source": str(args.reference_detail),
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {key: value for key, value in output.items() if key != "methods"}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
