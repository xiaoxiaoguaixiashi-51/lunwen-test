import json
import tempfile
import unittest
from pathlib import Path

from src.core.batch_runner import load_method_list


class BatchRunnerTest(unittest.TestCase):
    def test_load_method_list_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "methods.json"
            path.write_text(json.dumps([{"id": "one", "target": "A.java"}]), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_method_list(str(path))

    def test_load_method_list_accepts_valid_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "methods.json"
            path.write_text(
                json.dumps([{"id": "one", "target": "A.java", "method": "m"}]),
                encoding="utf-8",
            )

            items = load_method_list(str(path))
            self.assertEqual("one", items[0]["id"])


if __name__ == "__main__":
    unittest.main()
