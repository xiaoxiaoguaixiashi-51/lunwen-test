import csv
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_runtime_failures import (
    analyze_failures,
    classify_failure,
    extract_compile_evidence,
    write_category_summary,
)


class AnalyzeRuntimeFailuresTest(unittest.TestCase):
    def test_classifies_java_version_failure(self):
        category, evidence = classify_failure("Java 11 is required!\nCompilation failed in require")

        self.assertEqual("environment_java_version", category)
        self.assertIn("Java 11", evidence)

    def test_classifies_compile_failure_from_javac_line(self):
        category, evidence = classify_failure("[javac] Foo.java:12: cannot find symbol\n")

        self.assertEqual("compile_failure", category)
        self.assertIn("cannot find symbol", evidence)

    def test_extract_compile_evidence_skips_generic_compiling_line(self):
        log = """
[javac] Compiling 1 source file to /tmp/target/tests
[javac] /tmp/DemoTest.java:10: error: cannot find symbol
[javac]     missing();
"""

        evidence = extract_compile_evidence(log)

        self.assertIn("cannot find symbol", evidence)
        self.assertNotIn("Compiling 1 source file", evidence)

    def test_classifies_harness_failure(self):
        category, evidence = classify_failure("Cannot run tests! at /root/defects4j/framework/bin/d4j/d4j-test line 135.")

        self.assertEqual("compile_or_harness_failure", category)
        self.assertIn("Cannot run tests", evidence)

    def test_classifies_security_failure(self):
        category, evidence = classify_failure("java.security.AccessControlException: access denied")

        self.assertEqual("runtime_security_failure", category)
        self.assertIn("AccessControlException", evidence)

    def test_classifies_assertion_failure(self):
        category, evidence = classify_failure("java.lang.AssertionError: expected:<1> but was:<2>")

        self.assertEqual("oracle_assertion_failure", category)
        self.assertIn("expected", evidence)

    def test_analyze_failures_reads_failed_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "failed.log"
            log.write_text("java.lang.AssertionError: expected:<1> but was:<2>", encoding="utf-8")
            summary = root / "runtime_summary.csv"
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "source_file",
                        "test_class",
                        "test_method",
                        "status",
                        "failing_tests",
                        "return_code",
                        "log_file",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "source_file": "GeneratedTest.java",
                        "test_class": "org.example.GeneratedTest",
                        "test_method": "testGenerated",
                        "status": "failed",
                        "failing_tests": "1",
                        "return_code": "0",
                        "log_file": str(log),
                    }
                )
                writer.writerow(
                    {
                        "source_file": "GeneratedTest.java",
                        "test_class": "org.example.GeneratedTest",
                        "test_method": "testPassed",
                        "status": "passed",
                        "failing_tests": "0",
                        "return_code": "0",
                        "log_file": str(log),
                    }
                )

            rows = analyze_failures(str(summary))

            self.assertEqual(1, len(rows))
            self.assertEqual("oracle_assertion_failure", rows[0]["category"])

    def test_write_category_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "categories.md"
            write_category_summary(
                [
                    {"category": "compile_failure"},
                    {"category": "compile_failure"},
                    {"category": "oracle_assertion_failure"},
                ],
                str(output),
            )

            text = output.read_text(encoding="utf-8")
            self.assertIn("| compile_failure | 2 |", text)
            self.assertIn("| **Total** | **3** |", text)


if __name__ == "__main__":
    unittest.main()
