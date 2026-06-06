import unittest

from src.utils.llm_output import extract_fenced_block


class LlmOutputTest(unittest.TestCase):
    def test_extracts_closed_language_fence(self):
        response = "Here is code:\n```java\nclass A {}\n```\nDone"
        self.assertEqual("class A {}", extract_fenced_block(response, "java"))

    def test_tolerates_missing_closing_fence(self):
        response = "```java\nclass A {"
        self.assertEqual("class A {", extract_fenced_block(response, "java"))

    def test_strips_generic_fence_language_hint(self):
        response = "```json\n{\"ok\": true}\n```"
        self.assertEqual('{"ok": true}', extract_fenced_block(response))

    def test_returns_plain_response_without_fence(self):
        self.assertEqual("plain", extract_fenced_block(" plain "))


if __name__ == "__main__":
    unittest.main()
