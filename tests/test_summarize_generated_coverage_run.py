import tempfile
import unittest
from pathlib import Path

from scripts.summarize_generated_coverage_run import (
    summarize_directories,
    summarize_directory,
    write_csv,
    write_markdown,
)


class SummarizeGeneratedCoverageRunTest(unittest.TestCase):
    def test_summarize_directory_counts_statuses_and_max_coverage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_dir = Path(tmpdir) / "coverage_check_auto_example"
            coverage_dir.mkdir()
            (coverage_dir / "coverage_summary.csv").write_text(
                "\n".join(
                    [
                        "source_file,test_class,test_method,status,lines_total,lines_covered,conditions_total,conditions_covered,line_coverage,condition_coverage,return_code,log_file",
                        "A.java,org.example.ExampleTest,test_one,covered,10,5,4,1,50.0%,25.0%,0,one.log",
                        "A.java,org.example.ExampleTest,test_two,test_failed,10,7,4,2,70.0%,50.0%,0,two.log",
                        "A.java,org.example.ExampleTest,test_three,coverage_failed,,,,,,,1,three.log",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            row = summarize_directory(coverage_dir)

            self.assertEqual("org.example.ExampleTest", row["test_class"])
            self.assertEqual("1", row["covered"])
            self.assertEqual("1", row["test_failed"])
            self.assertEqual("1", row["coverage_failed"])
            self.assertEqual("3", row["total"])
            self.assertEqual("33.3%", row["coverage_success_rate"])
            self.assertEqual("70.0%", row["max_line_coverage"])
            self.assertEqual("50.0%", row["max_condition_coverage"])

    def test_summarize_directories_adds_total_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = self.write_summary(root / "first", ["covered", "covered", "test_failed"])
            second = self.write_summary(root / "second", ["coverage_failed", "covered"])

            rows = summarize_directories([first, second])

            self.assertEqual(3, len(rows))
            total = rows[-1]
            self.assertEqual("TOTAL", total["coverage_dir"])
            self.assertEqual("3", total["covered"])
            self.assertEqual("1", total["test_failed"])
            self.assertEqual("1", total["coverage_failed"])
            self.assertEqual("5", total["total"])
            self.assertEqual("60.0%", total["coverage_success_rate"])

    def test_write_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                {
                    "coverage_dir": "dir",
                    "test_class": "Class",
                    "covered": "1",
                    "test_failed": "0",
                    "coverage_failed": "0",
                    "environment_error": "0",
                    "timeout": "0",
                    "total": "1",
                    "coverage_success_rate": "100.0%",
                    "max_line_coverage": "10.0%",
                    "max_condition_coverage": "5.0%",
                }
            ]
            csv_path = Path(tmpdir) / "summary.csv"
            md_path = Path(tmpdir) / "summary.md"

            write_csv(rows, csv_path)
            write_markdown(rows, md_path)

            self.assertIn("coverage_dir,test_class", csv_path.read_text(encoding="utf-8"))
            self.assertIn("| coverage_dir | test_class |", md_path.read_text(encoding="utf-8"))

    def write_summary(self, coverage_dir: Path, statuses: list[str]) -> Path:
        coverage_dir.mkdir()
        lines = [
            "source_file,test_class,test_method,status,lines_total,lines_covered,conditions_total,conditions_covered,line_coverage,condition_coverage,return_code,log_file"
        ]
        for index, status in enumerate(statuses):
            lines.append(
                f"A.java,org.example.Test{coverage_dir.name},test_{index},{status},10,1,4,1,10.0%,25.0%,0,{index}.log"
            )
        (coverage_dir / "coverage_summary.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return coverage_dir


if __name__ == "__main__":
    unittest.main()
