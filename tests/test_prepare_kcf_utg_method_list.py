import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_kcf_utg_method_list import prepare


class PrepareKcfUtgMethodListTest(unittest.TestCase):
    def test_builds_runner_fields_without_complexity_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            fields = {
                "method": "run",
                "class_name": "Example",
                "package": "p",
                "fqcn": "p.Example",
                "project_name": "P",
                "project_version": "1",
                "java": 8,
                "target_relative": "src/main/java/p/Example.java",
                "source_root": "/project/src/main/java",
                "source_root_relative": "src/main/java",
            }
            rows = []
            for project_index in range(2):
                for method_index in range(2):
                    rows.append({
                        **fields,
                        "id": f"p{project_index}-m{method_index}",
                        "target": f"/project{project_index}/Example.java",
                        "project_id": f"p{project_index}",
                        "dcci": 99,
                        "mdci": 99,
                    })
            path.write_text(json.dumps(rows), encoding="utf-8")

            methods, card = prepare(path, expected_methods=4, expected_projects=2)

            self.assertEqual(4, len(methods))
            self.assertNotIn("dcci", methods[0])
            self.assertNotIn("mdci", methods[0])
            self.assertEqual({"p0": 2, "p1": 2}, card["project_counts"])
            self.assertEqual(64, len(card["source_manifest_sha256"]))

    def test_rejects_wrong_project_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected 41 unique methods"):
                prepare(path)


if __name__ == "__main__":
    unittest.main()
