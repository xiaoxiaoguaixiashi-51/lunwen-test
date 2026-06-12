import tempfile
import unittest
from pathlib import Path

from scripts.run_defects4j_generated_tests import (
    MethodRun,
    discover_generated_tests,
    parse_failing_tests,
    parse_generated_test,
    write_class_summary,
)


class RunDefects4jGeneratedTestsTest(unittest.TestCase):
    def test_parse_generated_test_extracts_package_class_and_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ExampleTest.java"
            path.write_text(
                """
package org.example;

import org.junit.Test;

public class ExampleTest {
    @Test
    public void test_one() {}

    @Test(expected = IllegalArgumentException.class)
    public void test_two() {}
}
""",
                encoding="utf-8",
            )

            parsed = parse_generated_test(path)

            self.assertEqual("org.example", parsed.package)
            self.assertEqual("ExampleTest", parsed.class_name)
            self.assertEqual("org.example.ExampleTest", parsed.fqcn)
            self.assertEqual(["test_one", "test_two"], parsed.methods)

    def test_parse_generated_test_uses_default_package_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "NoPackageTest.java"
            path.write_text(
                """
import org.junit.Test;

public class NoPackageTest {
    @Test
    public void test_missing_package() {}
}
""",
                encoding="utf-8",
            )

            parsed = parse_generated_test(path, default_package="org.example")

            self.assertEqual("org.example", parsed.package)
            self.assertEqual("org.example.NoPackageTest", parsed.fqcn)

    def test_discover_generated_tests_reads_nested_batch_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            item_dir = root / "method-one"
            item_dir.mkdir()
            (item_dir / "GeneratedTest.java").write_text(
                """
package org.example;
import org.junit.Test;
public class GeneratedTest {
    @Test
    public void test_generated() {}
}
""",
                encoding="utf-8",
            )

            tests = discover_generated_tests(root)

            self.assertEqual(1, len(tests))
            self.assertEqual("org.example.GeneratedTest", tests[0].fqcn)

    def test_parse_failing_tests(self):
        self.assertEqual(0, parse_failing_tests("Running ant\nFailing tests: 0\n"))
        self.assertEqual(3, parse_failing_tests("Failing tests: 3\n  - a::b"))
        self.assertIsNone(parse_failing_tests("Cannot run tests!"))

    def test_write_class_summary_groups_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "class_summary.md"
            rows = [
                MethodRun("A.java", "org.example.ATest", "test_one", "passed", 0, 0, "one.log"),
                MethodRun("A.java", "org.example.ATest", "test_two", "failed", 1, 0, "two.log"),
                MethodRun("B.java", "org.example.BTest", "test_one", "passed", 0, 0, "three.log"),
            ]

            write_class_summary(rows, output)

            text = output.read_text(encoding="utf-8")
            self.assertIn("| org.example.ATest | 1 | 2 | 50.0% |", text)
            self.assertIn("| org.example.BTest | 1 | 1 | 100.0% |", text)
            self.assertIn("| **Total** | **2** | **3** | **66.7%** |", text)


if __name__ == "__main__":
    unittest.main()
