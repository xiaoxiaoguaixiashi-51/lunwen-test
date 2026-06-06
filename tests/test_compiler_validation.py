import unittest

from src.utils.compiler import JavaCompiler


class CompilerValidationTest(unittest.TestCase):
    def test_empty_test_code_fails(self):
        result = JavaCompiler().compile_test("")

        self.assertFalse(result.success)
        self.assertIn("empty", result.errors)

    def test_test_code_without_class_fails(self):
        result = JavaCompiler().compile_test("import java.util.*;")

        self.assertFalse(result.success)
        self.assertIn("class declaration", result.errors)


if __name__ == "__main__":
    unittest.main()
