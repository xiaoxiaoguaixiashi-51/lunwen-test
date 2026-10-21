import json
import tempfile
import unittest
from pathlib import Path

from src.core.pipeline import Pipeline, PipelineResult
from src.utils.compiler import CompileResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class RecordingLLMClient:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs))
        if "Retrieved Dependency Construction Knowledge" in user_prompt:
            return """```json
{
  "test_class_name": "UserServiceTest",
  "setup": {"mocks": [], "fixtures": []},
  "test_cases": [{"name": "test_kg_guided", "scenario": "uses retrieved knowledge", "inputs": {}, "mock_setup": [], "assertions": [], "priority": "high"}]
}
```"""
        if "测试计划" in user_prompt:
            return """```json
{
  "test_class_name": "UserServiceTest",
  "setup": {"mocks": [], "fixtures": []},
  "test_cases": [{"name": "test_default", "scenario": "default", "inputs": {}, "mock_setup": [], "assertions": [], "priority": "high"}]
}
```"""
        if "JUnit 5" in user_prompt:
            return """```java
class UserServiceTest {
    void generatedTest() {}
}
```"""
        return """```json
{"dependency_summary": "UserService dependencies", "mock_candidates": [], "test_challenges": [], "suggested_test_scenarios": []}
```"""


class PassingCompiler:
    def compile_test(self, test_code, source_file=None, classpath=None):
        return CompileResult(True, "ok", "", 0)


class PipelineKgRetrievalTest(unittest.TestCase):
    def test_pipeline_injects_retrieved_knowledge_and_saves_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge.jsonl"
            knowledge_path.write_text(
                json.dumps({
                    "id": "userservice-update-email",
                    "class": "UserService",
                    "method": "updateUserEmail",
                    "problem": "mock repository cache and event publisher",
                    "test_strategy": "retrieve user then verify event",
                }),
                encoding="utf-8",
            )
            output_dir = Path(tmpdir) / "out"
            llm = RecordingLLMClient()
            pipeline = Pipeline(
                config={
                    "retrieval": {
                        "enabled": True,
                        "knowledge_path": str(knowledge_path),
                        "max_examples": 1,
                    },
                    "pipeline": {"feedback_enabled": True},
                },
                llm_client=llm,
                compiler=PassingCompiler(),
            )

            result = pipeline.run(str(TARGET), "updateUserEmail", output_dir=str(output_dir))

            self.assertTrue(result.success)
            self.assertEqual(["userservice-update-email"], [item["id"] for item in result.retrieved_knowledge])
            self.assertEqual("test_kg_guided", result.test_plan["test_cases"][0]["name"])
            report = json.loads((output_dir / "updateUserEmail_report.json").read_text(encoding="utf-8"))
            self.assertEqual(["userservice-update-email"], report["retrieved_knowledge_ids"])
            self.assertTrue(any("Retrieved Dependency Construction Knowledge" in call[1] for call in llm.calls))

    def test_save_results_uses_generated_class_name_for_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = Pipeline(
                config={"pipeline": {"feedback_enabled": True}},
                llm_client=RecordingLLMClient(),
                compiler=PassingCompiler(),
            )
            result = PipelineResult(
                target_file=str(TARGET),
                method_name="processArgs",
                final_test="package org.example;\npublic class ParserTest {}\n",
            )

            pipeline._save_results(result, tmpdir)

            self.assertTrue((Path(tmpdir) / "ParserTest.java").exists())


if __name__ == "__main__":
    unittest.main()
