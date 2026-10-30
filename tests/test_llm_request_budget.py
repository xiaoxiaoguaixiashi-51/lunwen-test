import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.core.llm_client import LLMClient, trace_target
from src.utils.request_budget import RequestBudget, BudgetExceeded


class ClientBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = {"max_calls_per_target": 1, "max_total_tokens_per_target": 100,
                       "max_input_tokens_per_call": 40, "max_output_tokens_per_call": 30}
        self.budget = RequestBudget(self.root / "budget.sqlite", self.policy)
        self.sdk = Mock()
        self.sdk.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1, total_tokens=11))

    def client(self, counter=lambda messages: 10, retries=0):
        module = SimpleNamespace(OpenAI=Mock(return_value=self.sdk))
        with patch.dict(sys.modules, {"openai": module}), patch.dict(os.environ, {
                "KCF_LLM_TRACE_PATH": str(self.root / "trace.jsonl")}), patch(
                "src.core.llm_client.load_budget", return_value=(self.budget, counter)):
            return LLMClient({"llm": {"base_url": "https://example.invalid", "api_key": "never-publish-this-key",
                                      "model": "offline-test", "max_retries": retries}})

    def events(self):
        return [json.loads(x) for x in (self.root / "trace.jsonl").read_text().splitlines()]

    def test_shared_stages_stop_before_second_provider_call_and_cap_output(self):
        first, second = self.client(), self.client()
        with trace_target("same-method"):
            self.assertEqual("OK", first.generate("system", "initial", max_tokens=8192))
            with self.assertRaises(BudgetExceeded):
                second.generate("system", "feedback", max_tokens=8192)
        self.assertEqual(1, self.sdk.chat.completions.create.call_count)
        self.assertEqual(30, self.sdk.chat.completions.create.call_args.kwargs["max_tokens"])
        events = self.events()
        self.assertTrue(events[0]["provider_call_attempted"])
        self.assertFalse(events[1]["provider_call_attempted"])
        self.assertEqual("budget_blocked", events[1]["status"])
        self.assertEqual(8192, events[0]["budget"]["requested_max_output"])

    def test_no_target_and_oversized_input_make_no_call(self):
        client = self.client()
        with self.assertRaises(BudgetExceeded):
            client.chat([{"role": "user", "content": "test"}])
        client = self.client(counter=lambda messages: 41)
        with trace_target("t"), self.assertRaises(BudgetExceeded):
            client.chat([{"role": "user", "content": "test"}])
        self.sdk.chat.completions.create.assert_not_called()

    def test_provider_error_charge_remains_unknown_and_no_retry(self):
        client = self.client()
        self.sdk.chat.completions.create.side_effect = RuntimeError("potential provider body never-publish-this-key")
        with trace_target("t"):
            with self.assertRaises(RuntimeError):
                client.chat([{"role": "user", "content": "test"}])
            with self.assertRaises(BudgetExceeded):
                client.chat([{"role": "user", "content": "test"}])
        self.assertEqual(1, self.sdk.chat.completions.create.call_count)
        self.assertEqual("unknown", self.events()[0]["budget_settlement"]["status"])
        self.assertNotIn("never-publish-this-key", (self.root / "trace.jsonl").read_text())

    def test_empty_response_still_charged(self):
        client = self.client()
        self.sdk.chat.completions.create.return_value.choices[0].message.content = ""
        with trace_target("t"), self.assertRaisesRegex(RuntimeError, "empty message"):
            client.chat([{"role": "user", "content": "test"}])
        event = self.events()[0]
        self.assertEqual("error", event["status"])
        self.assertEqual(11, event["budget_settlement"]["charged_tokens"])

    def test_enabled_budget_rejects_sdk_retries(self):
        with self.assertRaisesRegex(ValueError, "max_retries=0"):
            self.client(retries=2)
