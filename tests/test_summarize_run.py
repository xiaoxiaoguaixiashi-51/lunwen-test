import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_run import summarize_run, write_csv, write_markdown


class SummarizeRunTest(unittest.TestCase):
    def test_summarize_run_merges_status_and_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            item_dir = root / "demo-method"
            item_dir.mkdir()
            (root / "summary.json").write_text(
                json.dumps(
                    {
                        "total": 1,
                        "completed": 1,
                        "skipped": 0,
                        "failed": 0,
                        "items": [{"id": "demo-method", "status": "completed"}],
                    }
                ),
                encoding="utf-8",
            )
            (item_dir / "status.json").write_text(
                json.dumps(
                    {
                        "id": "demo-method",
                        "target": "Example.java",
                        "method": "targetMethod",
                        "status": "completed",
                        "success": True,
                        "iterations": 2,
                    }
                ),
                encoding="utf-8",
            )
            (item_dir / "targetMethod_report.json").write_text(
                json.dumps({"generated_test_length": 5010, "compile_attempts": 2}),
                encoding="utf-8",
            )

            rows = summarize_run(str(root))

            self.assertEqual(1, len(rows))
            self.assertEqual("demo-method", rows[0]["id"])
            self.assertEqual("targetMethod", rows[0]["method"])
            self.assertEqual(5010, rows[0]["generated_test_length"])
            self.assertEqual(2, rows[0]["compile_attempts"])

    def test_writes_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [{"id": "one", "method": "m", "status": "completed", "success": True}]
            csv_path = Path(tmpdir) / "summary.csv"
            md_path = Path(tmpdir) / "summary.md"

            write_csv(rows, str(csv_path))
            write_markdown(rows, str(md_path))

            self.assertIn("id,target,method,status", csv_path.read_text(encoding="utf-8"))
            self.assertIn("| id | target | method | status |", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
