"""Classify Defects4J generated-test runtime failures.

The runtime runner records one log per generated JUnit test method. This script
turns failed rows into a compact failure-analysis table for experiment reports.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


FAILURE_FIELDS = [
    "test_class",
    "test_method",
    "category",
    "evidence",
    "log_file",
]


def load_failed_rows(runtime_summary_csv: str) -> list[dict]:
    with Path(runtime_summary_csv).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row.get("status") == "failed"]


def analyze_failures(runtime_summary_csv: str) -> list[dict]:
    rows = []
    for row in load_failed_rows(runtime_summary_csv):
        log_file = row.get("log_file", "")
        log_text = Path(log_file).read_text(encoding="utf-8", errors="ignore") if log_file else ""
        category, evidence = classify_failure(log_text)
        rows.append(
            {
                "test_class": row.get("test_class", ""),
                "test_method": row.get("test_method", ""),
                "category": category,
                "evidence": evidence,
                "log_file": log_file,
            }
        )
    return rows


def classify_failure(log_text: str) -> tuple[str, str]:
    if "Java 11 is required!" in log_text:
        return "environment_java_version", "Defects4J requires Java 11"

    compile_match = re.search(r"\[javac\]\s+(.+)", log_text)
    if compile_match:
        return "compile_failure", clean_evidence(compile_match.group(1))

    if "Compilation failed in require" in log_text or "Cannot run tests!" in log_text:
        return "compile_or_harness_failure", first_matching_line(
            log_text, ["Compilation failed", "Cannot run tests!"]
        )

    if "java.security.AccessControlException" in log_text or "SecurityException" in log_text:
        return "runtime_security_failure", first_matching_line(log_text, ["AccessControlException", "SecurityException"])

    assertion = extract_assertion_evidence(log_text)
    if assertion:
        return "oracle_assertion_failure", assertion

    if "Exception" in log_text or "Error" in log_text:
        return "runtime_exception", first_matching_line(log_text, ["Exception", "Error"])

    failing = first_matching_line(log_text, ["Failing tests:"])
    if failing:
        return "test_failure_unspecified", failing

    return "unknown_failure", first_nonempty_line(log_text)


def extract_assertion_evidence(log_text: str) -> str:
    patterns = [
        r"junit\.framework\.AssertionFailedError:\s*(.+)",
        r"java\.lang\.AssertionError:\s*(.+)",
        r"expected:<.+?> but was:<.+?>",
    ]
    for pattern in patterns:
        match = re.search(pattern, log_text)
        if match:
            return clean_evidence(match.group(0))
    return ""


def first_matching_line(log_text: str, needles: list[str]) -> str:
    for line in log_text.splitlines():
        if any(needle in line for needle in needles):
            return clean_evidence(line)
    return ""


def first_nonempty_line(log_text: str) -> str:
    for line in log_text.splitlines():
        if line.strip():
            return clean_evidence(line)
    return ""


def clean_evidence(value: str) -> str:
    return " ".join(value.strip().split())[:240]


def write_csv(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FAILURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(FAILURE_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(FAILURE_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in FAILURE_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_category_summary(rows: list[dict], output_path: str):
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1

    lines = ["| category | count |", "| --- | ---: |"]
    for category in sorted(counts):
        lines.append(f"| {category} | {counts[category]} |")
    lines.append(f"| **Total** | **{len(rows)}** |")
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Analyze failed runtime checks")
    parser.add_argument("--runtime-summary", required=True, help="runtime_summary.csv from run_defects4j_generated_tests.py")
    parser.add_argument("--csv", help="Failure analysis CSV output")
    parser.add_argument("--markdown", help="Failure analysis Markdown output")
    parser.add_argument("--category-summary", help="Failure category summary Markdown output")
    args = parser.parse_args()

    rows = analyze_failures(args.runtime_summary)
    if args.csv:
        write_csv(rows, args.csv)
    if args.markdown:
        write_markdown(rows, args.markdown)
    if args.category_summary:
        write_category_summary(rows, args.category_summary)
    if not args.csv and not args.markdown and not args.category_summary:
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
