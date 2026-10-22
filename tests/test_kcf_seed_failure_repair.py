import csv
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_kcf_seed_failure_repair import prepare_seeds, main
from scripts.run_stage_b_ours_full_feedback import include_incremental_xml, validate_passing_seed_index, execution_dir_for


class SeedFailureRepairTest(unittest.TestCase):
    def test_new_mode_isolates_attempt_classes_logs_and_exec_files(self):
        first = execution_dir_for(Path("run"), 1, 0, True)
        repaired = execution_dir_for(Path("run"), 1, 1, True)
        self.assertNotEqual(first, repaired)
        self.assertEqual(execution_dir_for(Path("run"), 1, 0, False), execution_dir_for(Path("run"), 1, 1, False))

    def test_failed_or_unreviewed_xml_is_not_accepted_in_new_mode(self):
        failed = {"status": "test_failed", "xml_file": "diagnostic.xml"}
        self.assertFalse(include_incremental_xml(failed, True))
        self.assertTrue(include_incremental_xml(failed, False))
        self.assertTrue(include_incremental_xml({"status": "ok", "xml_file": "valid.xml"}, True))
        self.assertFalse(include_incremental_xml({"status": "ok", "xml_file": "valid.xml", "semantic_review_required": True}, True))

    def test_unreviewed_seed_cannot_enter_feedback_even_if_junit_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = root / "t.xml"
            xml.write_text("<report/>", encoding="utf-8")
            entry = {"id": "t", "status": "ok", "xml_name": "t.xml",
                     "xml_sha256": hashlib.sha256(xml.read_bytes()).hexdigest(), "semantic_review_required": True}
            index = root / "accepted_xml_index.json"
            index.write_text(json.dumps([entry]), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_passing_seed_index(root, {"t"})
            entry["semantic_review_required"] = False
            index.write_text(json.dumps([entry]), encoding="utf-8")
            validate_passing_seed_index(root, {"t"})
            xml.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_passing_seed_index(root, {"t"})

    def test_runtime_failure_is_queued_despite_full_diagnostic_coverage_and_dry_run_has_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects/p"
            project.mkdir(parents=True)
            target = project / "Target.java"
            target.write_text("class Target { int work() { return 1; } }", encoding="utf-8")
            source = root / "generated"
            source.mkdir()
            (source / "T.java").write_text("public class T { @org.junit.Test public void a() { org.junit.Assert.assertEquals(2, 1); } }", encoding="utf-8")
            logs = root / "execution"
            logs.mkdir()
            (logs / "junit.log").write_text("Tests run: 1, Failures: 1", encoding="utf-8")
            methods = [{"id": "t", "project_id": "p", "target": str(target), "method": "work",
                        "source_root": str(project), "source_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}]
            manifest = root / "methods.json"
            manifest.write_text(json.dumps(methods), encoding="utf-8")
            row = {"id": "t", "status": "test_failed", "test_class": "T", "source_dir": str(source),
                   "output_dir": str(logs), "xml_file": "", "focal_line_rate": "100.0%"}
            summary = root / "status.csv"
            with summary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            self.assertEqual("test_failed", prepare_seeds(methods, [summary])[0]["status"])
            config = root / "config.yaml"
            config.write_text("llm:\n  base_url: https://example.invalid\n  api_key: fake\n  model: fake\n", encoding="utf-8")
            output = root / "dry-run"
            args = ["seed-repair", "--method-list", str(manifest), "--coverage-summary", str(summary),
                    "--output-dir", str(output), "--projects-root", str(root / "projects"),
                    "--config", str(config), "--dry-run"]
            with patch("sys.argv", args), patch.dict(os.environ), patch("scripts.run_kcf_seed_failure_repair.LLMClient") as llm:
                main()
            llm.assert_not_called()
            data = json.loads((output / "failure_repair_summary.json").read_text(encoding="utf-8"))
            self.assertEqual("planned_failure_repair", data[0]["status"])
