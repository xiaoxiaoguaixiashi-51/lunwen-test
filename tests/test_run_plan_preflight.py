import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from scripts.preflight_kcf_run_plan import template, audit_plan, ARMS


class RunPlanPreflightTest(unittest.TestCase):
    def fixture(self, root):
        plan = template(root / "fresh-run")
        config_root = root / "fresh-run/configs"
        config_root.mkdir(parents=True)
        tokenizer = root / "tokenizer.json"
        tokenizer.write_text('{"fixture": true}')
        knowledge = root / "knowledge.jsonl"
        knowledge.write_text('{"id":"example"}\n')
        configs = {}
        for arm in ARMS:
            config = {"llm": {"base_url": "https://secret-endpoint.invalid", "model": "fixture-model", "api_key": "secret-sentinel",
                              "temperature": 0.2, "max_tokens": 50, "max_retries": 0, "timeout": 120},
                      "request_budget": {"ledger_path": str(root / "fresh-run" / arm / "budget.sqlite"),
                                         "tokenizer_json": str(tokenizer), "tokenizer_sha256": hashlib.sha256(tokenizer.read_bytes()).hexdigest(),
                                         "framing_reserve": 256, "max_calls_per_target": 12, "max_total_tokens_per_target": 20000,
                                         "max_input_tokens_per_call": 1000, "max_output_tokens_per_call": 50},
                      "pipeline": {"feedback_enabled": True, "max_fix_iterations": 3},
                      "retrieval": {"enabled": arm != "A1", "knowledge_path": str(knowledge), "max_examples": 3},
                      "static_guard": {"enabled": arm != "A3"}, "java": {"compile_timeout": 30}}
            path = config_root / (arm + ".yaml")
            path.write_text(yaml.safe_dump(config))
            configs[arm] = (path, config)
        return plan, configs

    def test_valid_plan_is_read_only_and_not_formal_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, _ = self.fixture(root)
            before = set(root.rglob("*"))
            with patch("socket.socket", side_effect=AssertionError("no network")):
                result = audit_plan(plan)
            self.assertTrue(result["configuration_checks_passed"], result["issues"])
            self.assertFalse(result["formal_run_ready"])
            self.assertEqual(13, len(result["checked_stages"]))
            self.assertEqual(before, set(root.rglob("*")))
            self.assertNotIn("secret-sentinel", json.dumps(result))
            self.assertNotIn("secret-endpoint", json.dumps(result))
            self.assertFalse(list(root.rglob("*.sqlite")))

    def test_detects_stage_ledger_split_and_cross_arm_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, configs = self.fixture(root)
            path, config = configs["Full"]
            split = copy.deepcopy(config)
            split["request_budget"]["ledger_path"] = str(root / "other-ledger.sqlite")
            different = root / "split.yaml"
            different.write_text(yaml.safe_dump(split))
            plan["jobs"][1]["config"] = str(different)
            self.assertIn("Full:seed_repair:cross_stage_config_or_ledger_mismatch", audit_plan(plan)["issues"])
            plan["jobs"][1]["config"] = str(path)
            a1_path, a1 = configs["A1"]
            a1["request_budget"]["ledger_path"] = config["request_budget"]["ledger_path"]
            a1_path.write_text(yaml.safe_dump(a1))
            self.assertTrue(any("ledger_shared_between_arms" in issue for issue in audit_plan(plan)["issues"]))

    def test_detects_flags_model_knowledge_and_output_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, configs = self.fixture(root)
            plan["jobs"][5]["ablation_flags"] = []  # A1 feedback requires both retrieval flags.
            plan["jobs"][6]["output_dir"] = plan["jobs"][0]["output_dir"]
            path, config = configs["A2"]
            config["llm"]["temperature"] = 0.8
            config["retrieval"]["max_examples"] = 4
            path.write_text(yaml.safe_dump(config))
            issues = audit_plan(plan)["issues"]
            self.assertIn("A1:feedback:ablation_flags_mismatch", issues)
            self.assertIn("A2:initial:output_reused_or_exists", issues)
            self.assertIn("A2:initial:cross_arm_model_or_budget_mismatch", issues)
            self.assertIn("A2:initial:cross_arm_knowledge_or_pipeline_mismatch", issues)

    def test_missing_config_incomplete_plan_and_changed_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, configs = self.fixture(root)
            (root / "tokenizer.json").write_text("changed")
            self.assertTrue(any("tokenizer_missing_or_changed" in issue for issue in audit_plan(plan)["issues"]))
            configs["Full"][0].unlink()
            self.assertIn("Full:initial:config_missing", audit_plan(plan)["issues"])
            plan["jobs"].pop()
            with self.assertRaises(ValueError):
                audit_plan(plan)


if __name__ == "__main__":
    unittest.main()
