import json
import tempfile
import unittest
from pathlib import Path

from src.utils.experiment_metadata import redact_secrets, write_run_metadata


class ExperimentMetadataTest(unittest.TestCase):
    def test_redacts_nested_secrets(self):
        value = {
            "llm": {"api_key": "secret", "model": "model-x"},
            "nested": [{"password": "pw", "value": 3}],
        }

        self.assertEqual(
            {
                "llm": {"api_key": "<redacted>", "model": "model-x"},
                "nested": [{"password": "<redacted>", "value": 3}],
            },
            redact_secrets(value),
        )

    def test_writes_hashes_settings_and_redacted_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            methods = root / "methods.json"
            config = root / "config.yaml"
            knowledge = root / "knowledge.jsonl"
            methods.write_text("[]", encoding="utf-8")
            config.write_text("llm:\n  api_key: hidden\n", encoding="utf-8")
            knowledge.write_text('{"id":"k1"}\n', encoding="utf-8")

            target = write_run_metadata(
                root / "run",
                stage="initial_generation",
                method_list=methods,
                config_path=config,
                config={"llm": {"api_key": "hidden", "model": "model-x"}},
                knowledge_path=knowledge,
                settings={"knowledge_retrieval_enabled": False},
            )

            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(64, len(data["method_list_sha256"]))
            self.assertEqual(64, len(data["config_sha256"]))
            self.assertEqual(64, len(data["knowledge_sha256"]))
            self.assertEqual("<redacted>", data["config_redacted"]["llm"]["api_key"])
            self.assertFalse(data["effective_settings"]["knowledge_retrieval_enabled"])
            self.assertNotIn("hidden", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
