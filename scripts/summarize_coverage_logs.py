"""Summarize Defects4J coverage logs into CSV/Markdown tables."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


COVERAGE_FIELDS = [
    "test_method",
    "lines_total",
    "lines_covered",
    "conditions_total",
    "conditions_covered",
    "line_coverage",
    "condition_coverage",
    "log_file",
]


def parse_coverage_log(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "test_method": path.name.replace(".coverage.log", ""),
        "lines_total": extract_int(text, r"Lines total:\s*(\d+)"),
        "lines_covered": extract_int(text, r"Lines covered:\s*(\d+)"),
        "conditions_total": extract_int(text, r"Conditions total:\s*(\d+)"),
        "conditions_covered": extract_int(text, r"Conditions covered:\s*(\d+)"),
        "line_coverage": extract_percent(text, r"Line coverage:\s*([0-9.]+%)"),
        "condition_coverage": extract_percent(text, r"Condition coverage:\s*([0-9.]+%)"),
        "log_file": str(path),
    }


def summarize_coverage_logs(log_dir: str) -> list[dict]:
    root = Path(log_dir)
    rows = [parse_coverage_log(path) for path in sorted(root.glob("*.coverage.log"))]
    return rows


def extract_int(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def extract_percent(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def write_csv(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(COVERAGE_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(COVERAGE_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in COVERAGE_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Summarize Defects4J coverage logs")
    parser.add_argument("--log-dir", required=True, help="Directory containing *.coverage.log files")
    parser.add_argument("--csv", help="CSV output path")
    parser.add_argument("--markdown", help="Markdown output path")
    args = parser.parse_args()

    rows = summarize_coverage_logs(args.log_dir)
    if args.csv:
        write_csv(rows, args.csv)
    if args.markdown:
        write_markdown(rows, args.markdown)
    if not args.csv and not args.markdown:
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
