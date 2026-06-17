import unittest
from unittest.mock import patch

from src.agents.generation_agent import GenerationAgent


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs))
        return """```java
class ExampleTest {
}
```"""


class GenerationAgentTest(unittest.TestCase):
    def test_defaults_to_junit5_for_demo_projects(self):
        llm = RecordingLLM()
        agent = GenerationAgent(llm)

        agent.generate({}, "class Example {}", {}, source_file="examples/java-demo/src/main/java/Example.java")

        system_prompt, user_prompt, _ = llm.calls[0]
        self.assertIn("JUnit 5", system_prompt)
        self.assertIn("JUnit 5", user_prompt)

    def test_uses_junit4_for_defects4j_projects(self):
        llm = RecordingLLM()
        agent = GenerationAgent(llm)

        agent.generate({}, "class Example {}", {}, source_file="/root/defects4j-work/Lang-1b/src/main/java/Example.java")

        system_prompt, user_prompt, _ = llm.calls[0]
        self.assertIn("JUnit 4", system_prompt)
        self.assertIn("JUnit 4", user_prompt)
        self.assertIn("禁止 import org.junit.jupiter.api", system_prompt)
        self.assertNotIn("Java 6 source-compatible", system_prompt)

    def test_java6_guard_prompt_is_opt_in_for_defects4j(self):
        llm = RecordingLLM()
        agent = GenerationAgent(llm)

        with patch.dict("os.environ", {"LUNWEN_ENABLE_JAVA6_GUARD": "1"}):
            agent.generate({}, "class Example {}", {}, source_file="/root/defects4j-work/Lang-1b/src/main/java/Example.java")

        system_prompt, _, _ = llm.calls[0]
        self.assertIn("Java 6 source-compatible", system_prompt)
        self.assertIn("diamond operators", system_prompt)

    def test_fix_prompt_keeps_junit4_constraint_for_defects4j(self):
        llm = RecordingLLM()
        agent = GenerationAgent(llm)

        agent.fix_compilation_error(
            "class ExampleTest {}",
            "package org.junit.jupiter.api does not exist",
            "class Example {}",
            source_file="/root/defects4j-work/Lang-1b/src/main/java/Example.java",
        )

        system_prompt, user_prompt, _ = llm.calls[0]
        self.assertIn("JUnit 4", system_prompt)
        self.assertIn("移除 org.junit.jupiter.api", user_prompt)


if __name__ == "__main__":
    unittest.main()
