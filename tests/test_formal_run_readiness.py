from pathlib import Path
import unittest
from scripts.audit_formal_run_readiness import audit, variant_matrix


class FormalReadinessTest(unittest.TestCase):
    def test_real_fixed_samples_and_cross_stage_flags(self):
        result = audit(Path(__file__).resolve().parents[1])
        self.assertFalse(result["formal_run_ready"])
        self.assertEqual(41, len(result["sample_use_ledger"]))
        self.assertEqual(35, result["evosuite_generation_class_count"])
        self.assertEqual(41, sum(len(r["focal_method_ids"]) for r in result["evosuite_class_groups"]))
        self.assertEqual(6, sum(r["known_rebuild_development_target"] for r in result["sample_use_ledger"]))
        self.assertFalse(any(r["independent_holdout_claim_allowed"] for r in result["sample_use_ledger"]))
        rows = {r["variant"]: r for r in result["variants"]}
        self.assertEqual(["--disable-coverage-gap-retrieval"], rows["A2"]["coverage_feedback_flags_required"])
        self.assertEqual([], rows["A2"]["seed_repair_flags_required"])
        self.assertIn("--disable-failure-repair-retrieval", rows["A1"]["seed_repair_flags_required"])
        self.assertEqual(["--disable-static-guard"], rows["A3"]["coverage_feedback_flags_required"])

    def test_wrong_initial_config_rejected(self):
        configs = {name: {"retrieval": {"enabled": True}, "static_guard": {"enabled": True},
                          "pipeline": {"feedback_enabled": True}} for name in ("Full", "A1", "A2", "A3")}
        with self.assertRaisesRegex(ValueError, "A1"):
            variant_matrix(configs)
