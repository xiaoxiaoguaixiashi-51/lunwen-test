import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.llm_client import LLMClient, trace_target


class LlmTraceTest(unittest.TestCase):
    def test_records_usage_target_and_redacts_key_without_real_network(self):
        secret = "test-secret-value"
        seen = {}

        def create(**kwargs):
            seen.update(kwargs)
            return SimpleNamespace(model="resolved-model", usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                                   choices=[SimpleNamespace(message=SimpleNamespace(content="answer " + secret), finish_reason="stop")])

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calls.jsonl"
            with patch.dict(os.environ, {"KCF_LLM_TRACE_PATH": str(path)}), patch.dict(
                "sys.modules", {"openai": SimpleNamespace(OpenAI=lambda **kwargs: fake_client)}
            ):
                client = LLMClient({"llm": {"base_url": "https://example.invalid/v1", "api_key": secret,
                                            "model": "requested-model", "max_retries": 0}})
                with trace_target("method-1"):
                    client.chat([{"role": "user", "content": "test"}], temperature=0)
            event = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("method-1", event["target_id"])
            self.assertEqual(15, event["usage"]["total_tokens"])
            self.assertEqual("resolved-model", event["response_model"])
            self.assertEqual(0, seen["temperature"])
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_failed_calls_are_counted_with_unknown_usage(self):
        def fail(**kwargs):
            raise TimeoutError("fake timeout")

        fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calls.jsonl"
            with patch.dict(os.environ, {"KCF_LLM_TRACE_PATH": str(path)}), patch.dict(
                "sys.modules", {"openai": SimpleNamespace(OpenAI=lambda **kwargs: fake)}
            ):
                client = LLMClient({"llm": {"base_url": "https://example.invalid/v1", "api_key": "test", "model": "m"}})
                with self.assertRaises(TimeoutError):
                    client.chat([])
            event = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("error", event["status"])
            self.assertIsNone(event["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
