import unittest
from pathlib import Path

from src.core.pipeline import Pipeline
from src.utils.compiler import CompileResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class FakeLLMClient:
    def __init__(self):
        self.fix_calls = 0

    def generate(self, system_prompt, user_prompt, **kwargs):
        if "编译失败" in user_prompt:
            self.fix_calls += 1
            return """```java
class UserServiceTest {
    void fixedTest() {}
}
```"""
        if "请生成测试计划" in user_prompt:
            return """```json
{
  "test_class_name": "UserServiceTest",
  "setup": {
    "mocks": ["userRepository", "cacheManager", "eventPublisher"],
    "fixtures": ["existing user"]
  },
  "test_cases": [
    {
      "name": "test_update_user_email",
      "scenario": "updates email and publishes event",
      "inputs": {"userId": "1", "newEmail": "new@example.com"},
      "mock_setup": [{"target": "userRepository", "method": "findById", "returns": "user"}],
      "assertions": [{"type": "assertEquals", "expected": "new@example.com"}],
      "priority": "high"
    }
  ]
}
```"""
        if "请生成完整的 JUnit 5 测试类代码" in user_prompt:
            return """```java
class UserServiceTest {
    void generatedTest() {}
}
```"""
        return """```json
{
  "dependency_summary": "UserService has repository, cache, event and time dependencies.",
  "mock_candidates": ["userRepository", "cacheManager", "eventPublisher"],
  "test_challenges": ["time dependency", "event payload assertion"],
  "suggested_test_scenarios": ["blank email", "missing user", "successful update"]
}
```"""


class FakeCompiler:
    def __init__(self):
        self.calls = 0
        self.received_source_files = []

    def compile_test(self, test_code, source_file=None, classpath=None):
        self.calls += 1
        self.received_source_files.append(source_file)
        if self.calls == 1:
            return CompileResult(False, "", "cannot find symbol", 1)
        return CompileResult(True, "ok", "", 0)


class PipelineOfflineTest(unittest.TestCase):
    def test_pipeline_runs_without_real_llm_or_java(self):
        llm = FakeLLMClient()
        compiler = FakeCompiler()
        pipeline = Pipeline(
            config={"pipeline": {"max_fix_iterations": 3, "feedback_enabled": True}},
            llm_client=llm,
            compiler=compiler,
        )

        result = pipeline.run(str(TARGET), "updateUserEmail")

        self.assertTrue(result.success)
        self.assertEqual(2, result.iterations)
        self.assertEqual(2, len(result.compile_results))
        self.assertIn("fixedTest", result.final_test)
        self.assertEqual(1, llm.fix_calls)
        self.assertEqual([str(TARGET), str(TARGET)], compiler.received_source_files)
        self.assertEqual("updateUserEmail", result.method_name)
        self.assertIn("test_cases", result.test_plan)


if __name__ == "__main__":
    unittest.main()
