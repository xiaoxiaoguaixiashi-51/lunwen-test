import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_run_analysis import build_analysis_rows, write_csv, write_markdown


class BuildRunAnalysisTest(unittest.TestCase):
    def test_merges_method_metadata_with_summary_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            methods = root / "methods.json"
            summary = root / "summary.csv"
            methods.write_text(
                json.dumps(
                    [
                        {
                            "id": "one",
                            "method": "targetMethod",
                            "source": "defects4j",
                            "dcci": 2.5,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "id",
                        "method",
                        "status",
                        "success",
                        "iterations",
                        "generated_test_length",
                        "compile_attempts",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "one",
                        "method": "targetMethod",
                        "status": "completed",
                        "success": "True",
                        "iterations": "2",
                        "generated_test_length": "1234",
                        "compile_attempts": "2",
                    }
                )

            rows = build_analysis_rows(str(methods), str(summary))

            self.assertEqual(1, len(rows))
            self.assertEqual(2.5, rows[0]["dcci"])
            self.assertEqual("defects4j", rows[0]["source"])
            self.assertEqual("compiled after 2 feedback rounds", rows[0]["repair_summary"])

    def test_writes_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                {
                    "id": "one",
                    "method": "m",
                    "source": "defects4j",
                    "dcci": 1.5,
                    "status": "completed",
                    "success": "True",
                    "iterations": "1",
                    "generated_test_length": "100",
                    "compile_attempts": "1",
                    "repair_summary": "compiled on first attempt",
                }
            ]
            csv_path = Path(tmpdir) / "analysis.csv"
            md_path = Path(tmpdir) / "analysis.md"

            write_csv(rows, str(csv_path))
            write_markdown(rows, str(md_path))

            self.assertIn("repair_summary", csv_path.read_text(encoding="utf-8"))
            self.assertIn("| id | method | source |", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
