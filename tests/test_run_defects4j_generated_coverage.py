import tempfile
import unittest
from pathlib import Path

from scripts.run_defects4j_generated_coverage import (
    CoverageRun,
    build_coverage_command,
    build_coverage_row,
    classify_coverage_status,
    filter_generated_tests,
    max_percent,
    row_to_dict,
    write_class_summary,
    write_instrument_file,
)
from scripts.run_defects4j_generated_tests import GeneratedTest


class RunDefects4jGeneratedCoverageTest(unittest.TestCase):
    def test_build_coverage_command_with_instrument_file(self):
        instrument_file = Path("/tmp/instrument.txt")
        cmd = build_coverage_command(
            "org.example.D4jGeneratedExampleTest",
            "test_one",
            instrument_file,
        )

        self.assertEqual(
            [
                "defects4j",
                "coverage",
                "-t",
                "org.example.D4jGeneratedExampleTest::test_one",
                "-i",
                str(instrument_file.resolve()),
            ],
            cmd,
        )

    def test_build_coverage_command_without_instrument_file(self):
        cmd = build_coverage_command("org.example.ExampleTest", "test_one")

        self.assertEqual(["defects4j", "coverage", "-t", "org.example.ExampleTest::test_one"], cmd)

    def test_write_instrument_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "coverage" / "instrument_classes.txt"

            written = write_instrument_file([" org.example.Foo ", "", "org.example.Bar"], output)

            self.assertEqual(output, written)
            self.assertEqual("org.example.Foo\norg.example.Bar\n", output.read_text(encoding="utf-8"))

    def test_filter_generated_tests_by_class_name(self):
        tests = [
            GeneratedTest(Path("A.java"), "org.example", "LocaleUtilsToLocaleTest", ["test_one"]),
            GeneratedTest(Path("B.java"), "org.example", "NumberUtilsCreateNumberTest", ["test_two"]),
        ]

        filtered = filter_generated_tests(tests, "LocaleUtils")

        self.assertEqual(1, len(filtered))
        self.assertEqual("LocaleUtilsToLocaleTest", filtered[0].class_name)

    def test_build_coverage_row_extracts_metrics(self):
        output = """
Running ant (coverage.report).............................................. OK
       Lines total: 98
     Lines covered: 21
  Conditions total: 72
Conditions covered: 15
     Line coverage: 21.4%
Condition coverage: 20.8%
"""

        row = build_coverage_row(Path("ExampleTest.java"), "org.example.ExampleTest", "test_one", output, 0, Path("x.log"))

        self.assertEqual("covered", row.status)
        self.assertEqual("98", row.lines_total)
        self.assertEqual("21", row.lines_covered)
        self.assertEqual("72", row.conditions_total)
        self.assertEqual("15", row.conditions_covered)
        self.assertEqual("21.4%", row.line_coverage)
        self.assertEqual("20.8%", row.condition_coverage)

    def test_classify_coverage_status(self):
        self.assertEqual("environment_error", classify_coverage_status("Java 11 is required!"))
        self.assertEqual("timeout", classify_coverage_status("Running\nTIMEOUT\n"))
        self.assertEqual("coverage_failed", classify_coverage_status("Cannot run tests!"))
        self.assertEqual(
            "test_failed",
            classify_coverage_status("Line coverage: 1.0%\nWARNING: Some tests failed\n"),
        )
        self.assertEqual("covered", classify_coverage_status("Line coverage: 1.0%\n"))

    def test_row_to_dict(self):
        row = CoverageRun(
            "ExampleTest.java",
            "org.example.ExampleTest",
            "test_one",
            "covered",
            "10",
            "5",
            "4",
            "2",
            "50.0%",
            "50.0%",
            0,
            "test.log",
        )

        data = row_to_dict(row)

        self.assertEqual("org.example.ExampleTest", data["test_class"])
        self.assertEqual("50.0%", data["line_coverage"])

    def test_write_class_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "coverage_class_summary.md"
            rows = [
                CoverageRun("A.java", "A", "test_one", "covered", "10", "4", "2", "1", "40.0%", "50.0%", 0, "1.log"),
                CoverageRun("A.java", "A", "test_two", "test_failed", "10", "7", "2", "2", "70.0%", "100.0%", 0, "2.log"),
                CoverageRun("B.java", "B", "test_one", "covered", "5", "1", "0", "0", "20.0%", "", 0, "3.log"),
            ]

            write_class_summary(rows, output)

            text = output.read_text(encoding="utf-8")
            self.assertIn("| A | 1 | 2 | 50.0% | 70.0% | 100.0% |", text)
            self.assertIn("| B | 1 | 1 | 100.0% | 20.0% |  |", text)
            self.assertIn("| **Total** | **2** | **3** | **66.7%** |", text)

    def test_max_percent(self):
        self.assertEqual("21.4%", max_percent(["4.1%", "21.4%", ""]))
        self.assertEqual("", max_percent(["", "not-a-percent"]))


if __name__ == "__main__":
    unittest.main()
