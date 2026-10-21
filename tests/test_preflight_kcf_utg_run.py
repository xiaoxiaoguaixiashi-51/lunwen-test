import json
import tempfile
import unittest
from pathlib import Path

from scripts.preflight_kcf_utg_run import run_preflight


class PreflightKcfUtgRunTest(unittest.TestCase):
    def test_accepts_rebased_targets_and_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            target = projects / "p" / "src" / "main" / "java" / "A.java"
            target.parent.mkdir(parents=True)
            target.write_text("class A {}", encoding="utf-8")
            methods = root / "methods.json"
            methods.write_text(json.dumps([{
                "id": "p-a", "project_id": "p", "target": "/old/A.java",
                "target_relative": "src/main/java/A.java"
            }]), encoding="utf-8")
            knowledge = root / "knowledge.jsonl"
            knowledge.write_text('{"id":"k"}\n', encoding="utf-8")

            result = run_preflight(methods, projects, knowledge, expected_method_count=1)

            self.assertTrue(result["ok"])
            self.assertEqual([], result["missing_target_ids"])

    def test_reports_missing_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            methods = root / "methods.json"
            methods.write_text("[]", encoding="utf-8")
            result = run_preflight(methods, root / "projects", root / "missing.jsonl")
            self.assertFalse(result["ok"])
            self.assertGreaterEqual(len(result["errors"]), 2)


if __name__ == "__main__":
    unittest.main()
