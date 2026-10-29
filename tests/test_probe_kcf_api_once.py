import unittest
from scripts.probe_kcf_api_once import safe_settings


class ApiProbeTest(unittest.TestCase):
    def config(self):
        return {"llm": {"base_url": "https://api.deepseek.com", "api_key": "test-secret",
                        "model": "deepseek-flash", "thinking": "disabled"}}

    def test_summary_does_not_contain_key(self):
        settings = safe_settings(self.config())
        self.assertNotIn("test-secret", str(settings))
        self.assertEqual(0, settings["probe_max_retries"])
        self.assertEqual(16, settings["probe_max_tokens"])

    def test_reject_unexpected_endpoint_and_model(self):
        for field, value in (("base_url", "https://example.com"), ("base_url", "https://api.deepseek.com?key=x"),
                             ("model", "other-model"), ("thinking", "enabled"), ("api_key", "your-api-key")):
            config = self.config()
            config["llm"][field] = value
            with self.assertRaises(ValueError):
                safe_settings(config)
