"""Classify failed Defects4J generated-test coverage commands.

The coverage runner writes one ``coverage_summary.csv`` per generated test
class. This script extracts non-covered rows and turns their logs into a
compact failure-analysis table for experiment reports.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


FAILURE_FIELDS = [
    "coverage_dir",
    "test_class",
    "test_method",
    "status",
    "category",
    "evidence",
    "log_file",
]


def analyze_coverage_failures(coverage_dirs: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for coverage_dir in coverage_dirs:
        summary_path = coverage_dir / "coverage_summary.csv"
        for row in read_csv(summary_path):
            status = row.get("status", "")
            if status == "covered":
                continue
            log_file = row.get("log_file", "")
            log_text = read_log(log_file)
            category, evidence = classify_coverage_failure(status, log_text)
            rows.append(
                {
                    "coverage_dir": str(coverage_dir),
                    "test_class": row.get("test_class", ""),
                    "test_method": row.get("test_method", ""),
                    "status": status,
                    "category": category,
                    "evidence": evidence,
                    "log_file": log_file,
                }
            )
    return rows


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_log(log_file: str) -> str:
    if not log_file:
        return ""
    path = Path(log_file)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def classify_coverage_failure(status: str, log_text: str) -> tuple[str, str]:
    if status == "environment_error" or "Java 11 is required!" in log_text:
        return "environment_java_version", "Defects4J requires Java 11"
    if status == "timeout" or "TIMEOUT" in log_text:
        return "timeout", first_matching_line(log_text, ["TIMEOUT"])

    source_level = first_matching_line(
        log_text,
        [
            "diamond operator is not supported in -source 6",
            "lambda expressions are not supported in -source",
            "method references are not supported in -source",
        ],
    )
    if source_level:
        return "source_level_incompatibility", source_level

    if "java.security.AccessControlException" in log_text or 'RuntimePermission" "setIO' in log_text:
        return "coverage_harness_security_failure", first_matching_line(
            log_text, ["AccessControlException", 'RuntimePermission" "setIO']
        )

    compile_evidence = extract_compile_evidence(log_text)
    if compile_evidence:
        return "coverage_compile_failure", compile_evidence

    assertion = extract_assertion_evidence(log_text)
    if assertion:
        return "oracle_assertion_failure", assertion

    if status == "test_failed" or "WARNING: Some tests failed" in log_text:
        return "test_failed_unspecified", first_matching_line(
            log_text, ["WARNING: Some tests failed", "Failing tests:"]
        )

    if "Couldn't obtain coverage results!" in log_text:
        return "coverage_harness_failure", first_matching_line(log_text, ["Couldn't obtain coverage results!"])

    if "Exception" in log_text or "Error" in log_text:
        return "runtime_exception", first_matching_line(log_text, ["Exception", "Error"])

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


def extract_compile_evidence(log_text: str) -> str:
    markers = [
        " error:",
        ": error:",
        "cannot find symbol",
        "Cannot compile test suite!",
        "has private access",
        "is not public",
        "cannot be accessed",
        "incompatible types",
        "no suitable method",
        "constructor ",
    ]
    for line in log_text.splitlines():
        if any(marker in line for marker in markers):
            return clean_evidence(line)
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


def write_csv(rows: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FAILURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| " + " | ".join(FAILURE_FIELDS) + " |",
        "| " + " | ".join(["---"] * len(FAILURE_FIELDS)) + " |",
    ]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in FAILURE_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_category_summary(rows: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(row["category"] for row in rows)
    lines = ["| category | count |", "| --- | ---: |"]
    for category in sorted(counts):
        lines.append(f"| {category} | {counts[category]} |")
    lines.append(f"| **Total** | **{len(rows)}** |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Analyze failed Defects4J coverage commands")
    parser.add_argument("--coverage-dir", action="append", required=True, help="Coverage output directory")
    parser.add_argument("--csv", help="Failure analysis CSV output")
    parser.add_argument("--markdown", help="Failure analysis Markdown output")
    parser.add_argument("--category-summary", help="Failure category summary Markdown output")
    args = parser.parse_args()

    rows = analyze_coverage_failures([Path(path) for path in args.coverage_dir])
    if args.csv:
        write_csv(rows, Path(args.csv))
    if args.markdown:
        write_markdown(rows, Path(args.markdown))
    if args.category_summary:
        write_category_summary(rows, Path(args.category_summary))
    if not args.csv and not args.markdown and not args.category_summary:
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
