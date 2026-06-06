"""Summarize batch-run outputs into CSV and Markdown tables."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SUMMARY_FIELDS = [
    "id",
    "target",
    "method",
    "status",
    "success",
    "iterations",
    "generated_test_length",
    "compile_attempts",
    "error",
]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _find_report(item_dir: Path, method: str | None) -> dict:
    candidates = []
    if method:
        candidates.append(item_dir / f"{method}_report.json")
    candidates.extend(sorted(item_dir.glob("*_report.json")))

    for candidate in candidates:
        if candidate.exists():
            return _read_json(candidate)
    return {}


def summarize_run(run_dir: str) -> list[dict]:
    """Build one flat result row per method in a batch output directory."""
    root = Path(run_dir)
    summary_path = root / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json under {root}")

    summary = _read_json(summary_path)
    rows = []
    for item in summary.get("items", []):
        method_id = item.get("id", "")
        item_dir = root / method_id
        status_path = item_dir / "status.json"
        status = _read_json(status_path) if status_path.exists() else item
        report = _find_report(item_dir, status.get("method") or item.get("method"))

        row = {
            "id": method_id,
            "target": status.get("target", item.get("target", "")),
            "method": status.get("method", item.get("method", "")),
            "status": status.get("status", item.get("status", "")),
            "success": status.get("success", ""),
            "iterations": status.get("iterations", ""),
            "generated_test_length": report.get("generated_test_length", ""),
            "compile_attempts": report.get("compile_attempts", ""),
            "error": status.get("error", ""),
        }
        rows.append(row)
    return rows


def write_csv(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(SUMMARY_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(SUMMARY_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in SUMMARY_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Summarize a batch-run result directory")
    parser.add_argument("--run-dir", required=True, help="Directory containing summary.json")
    parser.add_argument("--csv", help="CSV output path")
    parser.add_argument("--markdown", help="Markdown output path")
    args = parser.parse_args()

    rows = summarize_run(args.run_dir)
    if args.csv:
        write_csv(rows, args.csv)
    if args.markdown:
        write_markdown(rows, args.markdown)
    if not args.csv and not args.markdown:
        print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
