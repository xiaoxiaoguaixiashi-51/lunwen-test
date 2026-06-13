"""Summarize generated Defects4J coverage run directories.

The coverage runner writes one ``coverage_summary.csv`` per generated test
class run. This script combines selected run directories into one compact
table for reporting.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


SUMMARY_FIELDS = [
    "coverage_dir",
    "test_class",
    "covered",
    "test_failed",
    "coverage_failed",
    "environment_error",
    "timeout",
    "total",
    "coverage_success_rate",
    "max_line_coverage",
    "max_condition_coverage",
]


def summarize_directories(coverage_dirs: list[Path]) -> list[dict]:
    rows = [summarize_directory(path) for path in coverage_dirs]
    rows.append(total_row(rows))
    return rows


def summarize_directory(coverage_dir: Path) -> dict:
    summary_path = coverage_dir / "coverage_summary.csv"
    method_rows = read_csv(summary_path)
    if not method_rows:
        raise ValueError(f"No coverage rows found in {summary_path}")

    counts = Counter(row.get("status", "") for row in method_rows)
    total = len(method_rows)
    covered = counts.get("covered", 0)
    return {
        "coverage_dir": str(coverage_dir),
        "test_class": first_value(method_rows, "test_class"),
        "covered": str(covered),
        "test_failed": str(counts.get("test_failed", 0)),
        "coverage_failed": str(counts.get("coverage_failed", 0)),
        "environment_error": str(counts.get("environment_error", 0)),
        "timeout": str(counts.get("timeout", 0)),
        "total": str(total),
        "coverage_success_rate": format_rate(covered, total),
        "max_line_coverage": max_percent(row.get("line_coverage", "") for row in method_rows),
        "max_condition_coverage": max_percent(row.get("condition_coverage", "") for row in method_rows),
    }


def total_row(rows: list[dict]) -> dict:
    covered = sum_int(rows, "covered")
    total = sum_int(rows, "total")
    return {
        "coverage_dir": "TOTAL",
        "test_class": "",
        "covered": str(covered),
        "test_failed": str(sum_int(rows, "test_failed")),
        "coverage_failed": str(sum_int(rows, "coverage_failed")),
        "environment_error": str(sum_int(rows, "environment_error")),
        "timeout": str(sum_int(rows, "timeout")),
        "total": str(total),
        "coverage_success_rate": format_rate(covered, total),
        "max_line_coverage": max_percent(row.get("max_line_coverage", "") for row in rows),
        "max_condition_coverage": max_percent(row.get("max_condition_coverage", "") for row in rows),
    }


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def first_value(rows: list[dict], field: str) -> str:
    for row in rows:
        value = row.get(field, "")
        if value:
            return value
    return ""


def sum_int(rows: list[dict], field: str) -> int:
    total = 0
    for row in rows:
        value = row.get(field, "0")
        total += int(value or 0)
    return total


def format_rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def max_percent(values) -> str:
    parsed = []
    for value in values:
        if isinstance(value, str) and value.endswith("%"):
            try:
                parsed.append(float(value[:-1]))
            except ValueError:
                pass
    if not parsed:
        return ""
    return f"{max(parsed):.1f}%"


def write_csv(rows: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| " + " | ".join(SUMMARY_FIELDS) + " |",
        "| " + " | ".join(["---"] * len(SUMMARY_FIELDS)) + " |",
    ]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in SUMMARY_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Summarize generated Defects4J coverage run directories")
    parser.add_argument("--coverage-dir", action="append", required=True, help="Coverage output directory")
    parser.add_argument("--csv", help="CSV output path")
    parser.add_argument("--markdown", help="Markdown output path")
    args = parser.parse_args()

    rows = summarize_directories([Path(path) for path in args.coverage_dir])
    if args.csv:
        write_csv(rows, Path(args.csv))
    if args.markdown:
        write_markdown(rows, Path(args.markdown))
    if not args.csv and not args.markdown:
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
