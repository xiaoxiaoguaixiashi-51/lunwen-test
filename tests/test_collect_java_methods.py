import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_java_methods import collect_methods, safe_id


class CollectJavaMethodsTest(unittest.TestCase):
    def test_collects_public_non_overloaded_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "src" / "main" / "java"
            package_dir = root / "org" / "example"
            package_dir.mkdir(parents=True)
            (package_dir / "Sample.java").write_text(
                """
package org.example;

public class Sample {
  public int keep(int value) { return value + 1; }
  public int overloaded(int value) { return value; }
  public int overloaded(String value) { return value.length(); }
  private int ignore() { return 0; }
}
""",
                encoding="utf-8",
            )

            rows = collect_methods(root, "demo-project", "defects4j")

            self.assertEqual(1, len(rows))
            self.assertEqual("keep", rows[0]["method"])
            self.assertEqual("Sample", rows[0]["class_name"])
            self.assertEqual("org.example", rows[0]["package"])
            self.assertEqual("defects4j", rows[0]["source"])

    def test_safe_id_is_stable_slug(self):
        self.assertEqual("lang-1b-org-example-sample-keep", safe_id("Lang-1b", "org/example/Sample", "keep"))

    def test_rows_are_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "Sample.java").write_text("public class Sample { public void keep() {} }", encoding="utf-8")

            text = json.dumps(collect_methods(root, "demo", "local"))

            self.assertIn("keep", text)


if __name__ == "__main__":
    unittest.main()
