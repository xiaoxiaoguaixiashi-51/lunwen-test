import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.audit_kcf_feedback_round import audit_suite
from scripts.prepare_kcf_feedback_review import classify_suite
from scripts.run_stage_b_ours_full_feedback import run_initial_generated_test


class FeedbackAuditTest(unittest.TestCase):
    def test_api_error_without_completed_snapshot_remains_unknown_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "generated_tests/round1/t"
            folder.mkdir(parents=True)
            path = folder / "status.json"
            path.write_text(json.dumps({"id": "t", "project_id": "p", "round": 1, "status": "error"}), encoding="utf-8")
            row = audit_suite(root, path)
            self.assertEqual("error", row["final_status"])
            self.assertIsNone(row["junit"]["tests_run"])
            self.assertEqual("excluded", classify_suite(row))

    def test_new_generated_suite_cannot_bypass_checks_before_first_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            test = Path(tmp) / "T.java"
            test.write_text('public class T { @org.junit.Ignore @org.junit.Test public void a() { org.junit.Assert.assertEquals(1, 1); } }', encoding="utf-8")
            with patch("scripts.run_stage_b_ours_full_feedback.run_generated_test") as execute:
                result = run_initial_generated_test({}, test, "T", Path(tmp), SimpleNamespace(passing_only=True), {})
            execute.assert_not_called()
            self.assertEqual("integrity_rejected", result["status"])

    def test_review_and_failure_are_not_automatic_acceptance(self):
        good = {"final_status": "ok", "integrity": {"ok": True},
                "junit": {"tests_run": 2, "failures": 0}, "semantic_review_required": False}
        self.assertEqual("accepted", classify_suite(good))
        self.assertEqual("review", classify_suite({**good, "semantic_review_required": True}))
        self.assertEqual("excluded", classify_suite({**good, "final_status": "test_failed"}))
        self.assertEqual("excluded", classify_suite({**good, "junit": {"tests_run": 0, "failures": 0}}))
        self.assertEqual("excluded", classify_suite({**good, "integrity": {"ok": False}}))

    def test_audit_rejects_unknown_or_failed_xml_in_accepted_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "generated_tests/round1/t"
            folder.mkdir(parents=True)
            code = 'public class T { @org.junit.Test public void a() { org.junit.Assert.assertEquals(1, 1); } }'
            (folder / "attempt_0.java.txt").write_text(code, encoding="utf-8")
            execution = root / "incremental_jacoco/round1/attempt0/p/t"
            (execution / "xml").mkdir(parents=True)
            xml = execution / "xml/jacoco.xml"
            xml.write_text("<report/>", encoding="utf-8")
            (execution / "junit.log").write_text("OK (1 test)", encoding="utf-8")
            (folder / "attempt_0.json").write_text(json.dumps({"result": {"status": "ok"}}), encoding="utf-8")
            status = {"id": "t", "project_id": "p", "round": 1, "status": "ok",
                      "semantic_review_required": False, "xml_file": str(xml)}
            path = folder / "status.json"
            path.write_text(json.dumps(status), encoding="utf-8")
            adopted = root / "combined_xml/round1/t/jacoco.xml"
            adopted.parent.mkdir(parents=True)
            adopted.write_bytes(xml.read_bytes())
            self.assertTrue(audit_suite(root, path)["adopted_automatically"])
            path.write_text(json.dumps({**status, "semantic_review_required": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                audit_suite(root, path)
