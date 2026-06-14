import tempfile
import unittest
from pathlib import Path

from scripts.analyze_coverage_failures import (
    analyze_coverage_failures,
    classify_coverage_failure,
    write_category_summary,
)


class AnalyzeCoverageFailuresTest(unittest.TestCase):
    def test_classifies_source_level_incompatibility(self):
        category, evidence = classify_coverage_failure(
            "coverage_failed", "[javac] diamond operator is not supported in -source 6"
        )

        self.assertEqual("source_level_incompatibility", category)
        self.assertIn("diamond operator", evidence)

    def test_classifies_coverage_harness_security_failure(self):
        category, evidence = classify_coverage_failure(
            "coverage_failed",
            'java.security.AccessControlException: access denied ("java.lang.RuntimePermission" "setIO")',
        )

        self.assertEqual("coverage_harness_security_failure", category)
        self.assertIn("AccessControlException", evidence)

    def test_classifies_assertion_failure_before_unspecified_test_failure(self):
        category, evidence = classify_coverage_failure(
            "test_failed",
            "WARNING: Some tests failed\njava.lang.AssertionError: expected:<1> but was:<2>",
        )

        self.assertEqual("oracle_assertion_failure", category)
        self.assertIn("expected", evidence)

    def test_analyzes_non_covered_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            coverage_dir = root / "coverage_check_auto_example"
            coverage_dir.mkdir()
            log = coverage_dir / "failed.log"
            log.write_text("Cannot compile test suite!", encoding="utf-8")
            (coverage_dir / "coverage_summary.csv").write_text(
                "\n".join(
                    [
                        "source_file,test_class,test_method,status,lines_total,lines_covered,conditions_total,conditions_covered,line_coverage,condition_coverage,return_code,log_file",
                        f"A.java,org.example.GeneratedTest,test_fail,coverage_failed,,,,,,,1,{log}",
                        f"A.java,org.example.GeneratedTest,test_ok,covered,10,1,4,1,10.0%,25.0%,0,{log}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows = analyze_coverage_failures([coverage_dir])

            self.assertEqual(1, len(rows))
            self.assertEqual("coverage_compile_failure", rows[0]["category"])

    def test_write_category_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "summary.md"
            write_category_summary(
                [
                    {"category": "coverage_compile_failure"},
                    {"category": "coverage_compile_failure"},
                    {"category": "oracle_assertion_failure"},
                ],
                output,
            )

            text = output.read_text(encoding="utf-8")
            self.assertIn("| coverage_compile_failure | 2 |", text)
            self.assertIn("| **Total** | **3** |", text)


if __name__ == "__main__":
    unittest.main()
