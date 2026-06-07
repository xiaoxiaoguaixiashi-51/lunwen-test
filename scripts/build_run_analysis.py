"""Build an analysis table by merging method metadata with run summaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ANALYSIS_FIELDS = [
    "id",
    "method",
    "source",
    "dcci",
    "status",
    "success",
    "iterations",
    "generated_test_length",
    "compile_attempts",
    "repair_summary",
]


def load_method_metadata(methods_path: str) -> dict[str, dict]:
    items = json.loads(Path(methods_path).read_text(encoding="utf-8-sig"))
    if not isinstance(items, list):
        raise ValueError("Method metadata must be a JSON array")
    return {item["id"]: item for item in items}


def load_summary_rows(summary_csv_path: str) -> list[dict]:
    with Path(summary_csv_path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_analysis_rows(methods_path: str, summary_csv_path: str) -> list[dict]:
    metadata = load_method_metadata(methods_path)
    summary_rows = load_summary_rows(summary_csv_path)
    rows = []

    for summary in summary_rows:
        method_id = summary.get("id", "")
        meta = metadata.get(method_id, {})
        row = {
            "id": method_id,
            "method": summary.get("method") or meta.get("method", ""),
            "source": meta.get("source", ""),
            "dcci": meta.get("dcci", ""),
            "status": summary.get("status", ""),
            "success": summary.get("success", ""),
            "iterations": summary.get("iterations", ""),
            "generated_test_length": summary.get("generated_test_length", ""),
            "compile_attempts": summary.get("compile_attempts", ""),
        }
        row["repair_summary"] = summarize_repair(row)
        rows.append(row)

    return rows


def summarize_repair(row: dict) -> str:
    success = str(row.get("success", "")).lower() == "true"
    iterations = _to_int(row.get("iterations"))
    attempts = _to_int(row.get("compile_attempts")) or iterations

    if success and attempts <= 1:
        return "compiled on first attempt"
    if success:
        return f"compiled after {attempts} feedback rounds"
    if attempts:
        return f"failed after {attempts} feedback rounds"
    return "not available"


def write_csv(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANALYSIS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(ANALYSIS_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(ANALYSIS_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in ANALYSIS_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def main():
    parser = argparse.ArgumentParser(description="Build a run analysis table")
    parser.add_argument("--methods", required=True, help="Method list JSON with DCCI metadata")
    parser.add_argument("--summary-csv", required=True, help="summary_table.csv from summarize_run.py")
    parser.add_argument("--csv", help="Analysis CSV output path")
    parser.add_argument("--markdown", help="Analysis Markdown output path")
    args = parser.parse_args()

    rows = build_analysis_rows(args.methods, args.summary_csv)
    if args.csv:
        write_csv(rows, args.csv)
    if args.markdown:
        write_markdown(rows, args.markdown)
    if not args.csv and not args.markdown:
        print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
