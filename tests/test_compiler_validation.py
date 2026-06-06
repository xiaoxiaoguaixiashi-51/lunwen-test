import unittest
from pathlib import Path

from src.utils.compiler import JavaCompiler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class CompilerValidationTest(unittest.TestCase):
    def test_empty_test_code_fails(self):
        result = JavaCompiler().compile_test("")

        self.assertFalse(result.success)
        self.assertIn("empty", result.errors)

    def test_test_code_without_class_fails(self):
        result = JavaCompiler().compile_test("import java.util.*;")

        self.assertFalse(result.success)
        self.assertIn("class declaration", result.errors)

    def test_maven_source_root_is_inferred_for_source_file(self):
        compiler = JavaCompiler()
        cp_parts = compiler._classpath_for_source_file(str(TARGET))

        self.assertIn(str(PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java"), cp_parts)

    def test_splits_maven_test_dependencies_when_available(self):
        compiler = JavaCompiler()
        cp = f"/repo/junit.jar{__import__('os').pathsep}/repo/mockito.jar"
        compiler._maven_test_classpath = lambda project_root: cp

        cp_parts = compiler._classpath_for_source_file(str(TARGET))

        self.assertIn("/repo/junit.jar", cp_parts)
        self.assertIn("/repo/mockito.jar", cp_parts)


if __name__ == "__main__":
    unittest.main()
