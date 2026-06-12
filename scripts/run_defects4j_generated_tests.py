"""Run generated JUnit test methods inside a Defects4J checkout.

This script is intentionally focused on runtime validation after the pipeline
has already produced compilable tests. It copies generated test classes into a
Defects4J project's test tree, executes each generated test method with
``defects4j test -t Class::method``, and writes CSV/Markdown summaries.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


METHOD_PATTERN = re.compile(
    r"@Test(?:\s*\([^)]*\))?\s+public\s+void\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)
PACKAGE_PATTERN = re.compile(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^\s*public\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)


@dataclass
class GeneratedTest:
    source_path: Path
    package: str
    class_name: str
    methods: list[str]

    @property
    def fqcn(self) -> str:
        return f"{self.package}.{self.class_name}" if self.package else self.class_name


@dataclass
class MethodRun:
    source_file: str
    test_class: str
    test_method: str
    status: str
    failing_tests: int | None
    return_code: int
    log_file: str


SUMMARY_FIELDS = [
    "source_file",
    "test_class",
    "test_method",
    "status",
    "failing_tests",
    "return_code",
    "log_file",
]


def parse_generated_test(path: Path, default_package: str = "") -> GeneratedTest:
    text = path.read_text(encoding="utf-8")
    package_match = PACKAGE_PATTERN.search(text)
    class_match = CLASS_PATTERN.search(text)
    if not class_match:
        raise ValueError(f"Missing public class declaration in {path}")

    package = package_match.group(1) if package_match else default_package
    methods = METHOD_PATTERN.findall(text)
    if not methods:
        raise ValueError(f"No public JUnit test methods found in {path}")

    return GeneratedTest(
        source_path=path,
        package=package,
        class_name=class_match.group(1),
        methods=methods,
    )


def discover_generated_tests(run_dir: Path, default_package: str = "") -> list[GeneratedTest]:
    tests = []
    for path in sorted(run_dir.glob("*/*Test.java")):
        tests.append(parse_generated_test(path, default_package=default_package))
    return tests


def install_generated_test(test: GeneratedTest, defects4j_dir: Path, overwrite: bool = False) -> Path:
    package_path = Path(*test.package.split(".")) if test.package else Path()
    target_dir = defects4j_dir / "src" / "test" / "java" / package_path
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{test.class_name}.java"

    if target_path.exists() and not overwrite:
        existing = target_path.read_text(encoding="utf-8", errors="ignore")
        generated = test.source_path.read_text(encoding="utf-8")
        if existing != generated:
            raise FileExistsError(
                f"Refusing to overwrite existing test class: {target_path}. "
                "Use --overwrite to replace it."
            )

    shutil.copyfile(test.source_path, target_path)
    return target_path


def run_generated_tests(
    generated_tests: list[GeneratedTest],
    defects4j_dir: Path,
    output_dir: Path,
    overwrite: bool = False,
    timeout: int = 180,
) -> list[MethodRun]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[MethodRun] = []

    for test in generated_tests:
        install_generated_test(test, defects4j_dir, overwrite=overwrite)
        class_log_dir = output_dir / safe_name(test.fqcn)
        class_log_dir.mkdir(parents=True, exist_ok=True)

        for method in test.methods:
            log_path = class_log_dir / f"{method}.log"
            cmd = ["defects4j", "test", "-t", f"{test.fqcn}::{method}"]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(defects4j_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                return_code = proc.returncode
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") + (exc.stderr or "") + "\nTIMEOUT\n"
                return_code = -1

            log_path.write_text(output, encoding="utf-8")
            failing_tests = parse_failing_tests(output)
            status = classify_test_status(failing_tests)
            rows.append(
                MethodRun(
                    source_file=str(test.source_path),
                    test_class=test.fqcn,
                    test_method=method,
                    status=status,
                    failing_tests=failing_tests,
                    return_code=return_code,
                    log_file=str(log_path),
                )
            )

    return rows


def parse_failing_tests(output: str) -> int | None:
    match = re.search(r"Failing tests:\s*(\d+)", output)
    if not match:
        return None
    return int(match.group(1))


def classify_test_status(failing_tests: int | None) -> str:
    """Classify Defects4J single-test output.

    Defects4J can emit a non-zero process status even when the test log clearly
    reports ``Failing tests: 0``. The log result is the stable experimental
    signal we need for Test Pass Rate.
    """
    return "passed" if failing_tests == 0 else "failed"


def write_csv(rows: list[MethodRun], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row_to_dict(row))


def write_markdown(rows: list[MethodRun], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = "| " + " | ".join(SUMMARY_FIELDS) + " |"
    separator = "| " + " | ".join(["---"] * len(SUMMARY_FIELDS)) + " |"
    lines = [header, separator]
    for row in rows:
        values = [str(row_to_dict(row).get(field, "")).replace("|", "\\|") for field in SUMMARY_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_class_summary(rows: list[MethodRun], output_path: Path):
    by_class: dict[str, list[MethodRun]] = {}
    for row in rows:
        by_class.setdefault(row.test_class, []).append(row)

    lines = ["| test_class | passed | total | pass_rate |", "| --- | ---: | ---: | ---: |"]
    overall_passed = 0
    overall_total = 0
    for test_class in sorted(by_class):
        class_rows = by_class[test_class]
        total = len(class_rows)
        passed = sum(1 for row in class_rows if row.status == "passed")
        overall_passed += passed
        overall_total += total
        lines.append(f"| {test_class} | {passed} | {total} | {format_rate(passed, total)} |")

    lines.append(f"| **Total** | **{overall_passed}** | **{overall_total}** | **{format_rate(overall_passed, overall_total)}** |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def row_to_dict(row: MethodRun) -> dict:
    return {
        "source_file": row.source_file,
        "test_class": row.test_class,
        "test_method": row.test_method,
        "status": row.status,
        "failing_tests": "" if row.failing_tests is None else row.failing_tests,
        "return_code": row.return_code,
        "log_file": row.log_file,
    }


def format_rate(passed: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{passed / total * 100:.1f}%"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def main():
    parser = argparse.ArgumentParser(description="Run generated tests inside a Defects4J checkout")
    parser.add_argument("--run-dir", required=True, help="Batch run directory containing generated *Test.java files")
    parser.add_argument("--defects4j-dir", required=True, help="Defects4J project checkout directory")
    parser.add_argument("--output-dir", required=True, help="Directory for runtime logs and summaries")
    parser.add_argument(
        "--default-package",
        default="",
        help="Package to use for generated tests that omitted a package declaration",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing target test files")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per test method in seconds")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    defects4j_dir = Path(args.defects4j_dir)
    output_dir = Path(args.output_dir)

    generated_tests = discover_generated_tests(run_dir, default_package=args.default_package)
    rows = run_generated_tests(
        generated_tests,
        defects4j_dir,
        output_dir,
        overwrite=args.overwrite,
        timeout=args.timeout,
    )

    write_csv(rows, output_dir / "runtime_summary.csv")
    write_markdown(rows, output_dir / "runtime_summary.md")
    write_class_summary(rows, output_dir / "runtime_class_summary.md")

    passed = sum(1 for row in rows if row.status == "passed")
    total = len(rows)
    print(f"Runtime pass rate: {passed}/{total} ({format_rate(passed, total)})")
    print(f"Wrote summaries under {output_dir}")


if __name__ == "__main__":
    main()
