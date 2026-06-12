import tempfile
import unittest
from pathlib import Path

from scripts.summarize_coverage_logs import (
    parse_coverage_log,
    summarize_coverage_logs,
    write_csv,
    write_markdown,
)


class SummarizeCoverageLogsTest(unittest.TestCase):
    def test_parse_coverage_log_extracts_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_example.coverage.log"
            path.write_text(
                """
Running ant (coverage.report).............................................. OK
       Lines total: 98
     Lines covered: 13
  Conditions total: 72
Conditions covered: 8
     Line coverage: 13.3%
Condition coverage: 11.1%
""",
                encoding="utf-8",
            )

            row = parse_coverage_log(path)

            self.assertEqual("test_example", row["test_method"])
            self.assertEqual("98", row["lines_total"])
            self.assertEqual("13", row["lines_covered"])
            self.assertEqual("72", row["conditions_total"])
            self.assertEqual("8", row["conditions_covered"])
            self.assertEqual("13.3%", row["line_coverage"])
            self.assertEqual("11.1%", row["condition_coverage"])

    def test_summarize_coverage_logs_reads_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.coverage.log").write_text("Line coverage: 1.0%\n", encoding="utf-8")
            (root / "b.txt").write_text("Line coverage: 2.0%\n", encoding="utf-8")

            rows = summarize_coverage_logs(str(root))

            self.assertEqual(1, len(rows))
            self.assertEqual("a", rows[0]["test_method"])

    def test_writes_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                {
                    "test_method": "test_one",
                    "lines_total": "10",
                    "lines_covered": "5",
                    "conditions_total": "4",
                    "conditions_covered": "2",
                    "line_coverage": "50.0%",
                    "condition_coverage": "50.0%",
                    "log_file": "test_one.coverage.log",
                }
            ]
            csv_path = Path(tmpdir) / "coverage.csv"
            md_path = Path(tmpdir) / "coverage.md"

            write_csv(rows, str(csv_path))
            write_markdown(rows, str(md_path))

            self.assertIn("test_method,lines_total", csv_path.read_text(encoding="utf-8"))
            self.assertIn("| test_method | lines_total |", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
