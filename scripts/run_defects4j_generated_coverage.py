"""Run Defects4J coverage for generated JUnit test methods.

This script mirrors ``run_defects4j_generated_tests.py`` but executes
``defects4j coverage`` instead of ``defects4j test``. It is intended for the
coverage stage after generated tests have already been runtime-validated.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_defects4j_generated_tests import (
    GeneratedTest,
    build_subprocess_env,
    discover_generated_tests,
    format_rate,
    install_generated_test,
    parse_failing_tests,
    safe_name,
)


COVERAGE_FIELDS = [
    "source_file",
    "test_class",
    "test_method",
    "status",
    "lines_total",
    "lines_covered",
    "conditions_total",
    "conditions_covered",
    "line_coverage",
    "condition_coverage",
    "return_code",
    "log_file",
]


@dataclass
class CoverageRun:
    source_file: str
    test_class: str
    test_method: str
    status: str
    lines_total: str
    lines_covered: str
    conditions_total: str
    conditions_covered: str
    line_coverage: str
    condition_coverage: str
    return_code: int
    log_file: str


def run_generated_coverage(
    generated_tests: list[GeneratedTest],
    defects4j_dir: Path,
    output_dir: Path,
    instrument_file: Path | None = None,
    overwrite: bool = False,
    timeout: int = 240,
    java_home: str = "",
) -> list[CoverageRun]:
    output_dir.mkdir(parents=True, exist_ok=True)
    env = build_subprocess_env(java_home)
    rows: list[CoverageRun] = []

    for test in generated_tests:
        installed = install_generated_test(test, defects4j_dir, overwrite=overwrite)
        try:
            class_log_dir = output_dir / safe_name(installed.fqcn)
            class_log_dir.mkdir(parents=True, exist_ok=True)

            for method in installed.methods:
                log_path = class_log_dir / f"{method}.coverage.log"
                cmd = build_coverage_command(installed.fqcn, method, instrument_file)
                try:
                    proc = subprocess.run(
                        cmd,
                        cwd=str(defects4j_dir),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env,
                    )
                    output = (proc.stdout or "") + (proc.stderr or "")
                    return_code = proc.returncode
                except subprocess.TimeoutExpired as exc:
                    output = (exc.stdout or "") + (exc.stderr or "") + "\nTIMEOUT\n"
                    return_code = -1

                log_path.write_text(output, encoding="utf-8")
                rows.append(build_coverage_row(test.source_path, installed.fqcn, method, output, return_code, log_path))
        finally:
            installed.target_path.unlink(missing_ok=True)

    return rows


def filter_generated_tests(generated_tests: list[GeneratedTest], include_class_name: str = "") -> list[GeneratedTest]:
    if not include_class_name:
        return generated_tests
    return [test for test in generated_tests if include_class_name in test.class_name or include_class_name in test.fqcn]


def build_coverage_command(test_class: str, test_method: str, instrument_file: Path | None = None) -> list[str]:
    cmd = ["defects4j", "coverage", "-t", f"{test_class}::{test_method}"]
    if instrument_file:
        cmd.extend(["-i", str(instrument_file)])
    return cmd


def write_instrument_file(instrument_classes: list[str], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [value.strip() for value in instrument_classes if value.strip()]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output_path


def build_coverage_row(
    source_file: Path,
    test_class: str,
    test_method: str,
    output: str,
    return_code: int,
    log_path: Path,
) -> CoverageRun:
    return CoverageRun(
        source_file=str(source_file),
        test_class=test_class,
        test_method=test_method,
        status=classify_coverage_status(output),
        lines_total=extract_int(output, r"Lines total:\s*(\d+)"),
        lines_covered=extract_int(output, r"Lines covered:\s*(\d+)"),
        conditions_total=extract_int(output, r"Conditions total:\s*(\d+)"),
        conditions_covered=extract_int(output, r"Conditions covered:\s*(\d+)"),
        line_coverage=extract_percent(output, r"Line coverage:\s*([0-9.]+%)"),
        condition_coverage=extract_percent(output, r"Condition coverage:\s*([0-9.]+%)"),
        return_code=return_code,
        log_file=str(log_path),
    )


def classify_coverage_status(output: str) -> str:
    if "Java 11 is required!" in output:
        return "environment_error"
    if "TIMEOUT" in output:
        return "timeout"
    if not has_coverage_metrics(output):
        return "coverage_failed"
    failing_tests = parse_failing_tests(output)
    if failing_tests and failing_tests > 0:
        return "test_failed"
    if "WARNING: Some tests failed" in output:
        return "test_failed"
    return "covered"


def has_coverage_metrics(output: str) -> bool:
    return bool(re.search(r"Line coverage:\s*[0-9.]+%", output))


def extract_int(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def extract_percent(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def write_csv(rows: list[CoverageRun], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row_to_dict(row))


def write_markdown(rows: list[CoverageRun], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(COVERAGE_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(COVERAGE_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row_to_dict(row).get(field, "")).replace("|", "\\|") for field in COVERAGE_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_class_summary(rows: list[CoverageRun], output_path: Path):
    by_class: dict[str, list[CoverageRun]] = {}
    for row in rows:
        by_class.setdefault(row.test_class, []).append(row)

    lines = [
        "| test_class | covered | total | coverage_success_rate | max_line_coverage | max_condition_coverage |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    total_covered = 0
    total = 0
    for test_class in sorted(by_class):
        class_rows = by_class[test_class]
        covered = sum(1 for row in class_rows if row.status == "covered")
        total_covered += covered
        total += len(class_rows)
        lines.append(
            f"| {test_class} | {covered} | {len(class_rows)} | {format_rate(covered, len(class_rows))} | "
            f"{max_percent(row.line_coverage for row in class_rows)} | "
            f"{max_percent(row.condition_coverage for row in class_rows)} |"
        )

    lines.append(
        f"| **Total** | **{total_covered}** | **{total}** | **{format_rate(total_covered, total)}** |  |  |"
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def row_to_dict(row: CoverageRun) -> dict:
    return {
        "source_file": row.source_file,
        "test_class": row.test_class,
        "test_method": row.test_method,
        "status": row.status,
        "lines_total": row.lines_total,
        "lines_covered": row.lines_covered,
        "conditions_total": row.conditions_total,
        "conditions_covered": row.conditions_covered,
        "line_coverage": row.line_coverage,
        "condition_coverage": row.condition_coverage,
        "return_code": row.return_code,
        "log_file": row.log_file,
    }


def main():
    parser = argparse.ArgumentParser(description="Run Defects4J coverage for generated tests")
    parser.add_argument("--run-dir", required=True, help="Batch run directory containing generated *Test.java files")
    parser.add_argument("--defects4j-dir", required=True, help="Defects4J project checkout directory")
    parser.add_argument("--output-dir", required=True, help="Directory for coverage logs and summaries")
    parser.add_argument(
        "--default-package",
        default="",
        help="Package to use for generated tests that omitted a package declaration",
    )
    parser.add_argument(
        "--instrument-class",
        action="append",
        default=[],
        help="Fully-qualified class to instrument. Repeat for multiple classes.",
    )
    parser.add_argument(
        "--instrument-file",
        default="",
        help="Existing Defects4J instrument_classes file. Overrides --instrument-class when provided.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing target test files")
    parser.add_argument(
        "--include-class-name",
        default="",
        help="Only run generated test classes whose original class name or FQCN contains this text",
    )
    parser.add_argument("--timeout", type=int, default=240, help="Timeout per coverage run in seconds")
    parser.add_argument(
        "--java-home",
        default="",
        help="JAVA_HOME to force for defects4j subprocesses, e.g. /usr/lib/jvm/java-11-openjdk-amd64",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    defects4j_dir = Path(args.defects4j_dir)
    output_dir = Path(args.output_dir)

    instrument_file = Path(args.instrument_file) if args.instrument_file else None
    if not instrument_file and args.instrument_class:
        instrument_file = write_instrument_file(args.instrument_class, output_dir / "instrument_classes.txt")

    generated_tests = filter_generated_tests(
        discover_generated_tests(run_dir, default_package=args.default_package),
        include_class_name=args.include_class_name,
    )
    if not generated_tests:
        raise SystemExit(f"No generated test classes matched --include-class-name={args.include_class_name!r}")

    rows = run_generated_coverage(
        generated_tests,
        defects4j_dir,
        output_dir,
        instrument_file=instrument_file,
        overwrite=args.overwrite,
        timeout=args.timeout,
        java_home=args.java_home,
    )

    write_csv(rows, output_dir / "coverage_summary.csv")
    write_markdown(rows, output_dir / "coverage_summary.md")
    write_class_summary(rows, output_dir / "coverage_class_summary.md")

    covered = sum(1 for row in rows if row.status == "covered")
    total = len(rows)
    print(f"Coverage command success rate: {covered}/{total} ({format_rate(covered, total)})")
    print(f"Wrote coverage summaries under {output_dir}")


if __name__ == "__main__":
    main()
