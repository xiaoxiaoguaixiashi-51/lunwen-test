import unittest

from src.utils.java_compat import java6_compatibility_errors


class JavaCompatTest(unittest.TestCase):
    def test_rejects_real_lambda_expression(self):
        code = """
public class ExampleTest {
    Runnable r = () -> {};
}
"""
        errors = java6_compatibility_errors(code)

        self.assertTrue(any("lambda_expression" in error for error in errors))

    def test_ignores_arrow_and_colons_inside_string_literals(self):
        code = """
public class ExampleTest {
    String close = "-->";
    String label = "a::b";
}
"""
        errors = java6_compatibility_errors(code)

        self.assertFalse(any("lambda_expression" in error for error in errors))
        self.assertFalse(any("method_reference" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
