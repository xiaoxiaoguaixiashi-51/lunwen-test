import unittest
from unittest.mock import Mock, patch

from src.core.llm_client import LLMClient


class LLMClientTest(unittest.TestCase):
    @patch("builtins.__import__")
    def test_empty_content_is_error(self, mock_import):
        real_import = __import__

        def import_side_effect(name, *args, **kwargs):
            if name == "openai":
                module = Mock()
                module.OpenAI.return_value = Mock()
                return module
            return real_import(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect
        client = LLMClient({"llm": {"base_url": "http://example", "api_key": "key", "model": "model"}})

        message = Mock()
        message.content = ""
        message.reasoning_content = "thinking only"
        choice = Mock()
        choice.message = message
        choice.finish_reason = "length"
        client.client.chat.completions.create.return_value = Mock(choices=[choice])

        with self.assertRaisesRegex(RuntimeError, "empty message content"):
            client.chat([{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
