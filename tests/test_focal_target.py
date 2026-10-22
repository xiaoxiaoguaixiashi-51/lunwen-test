import tempfile
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import javalang
from src.utils.focal_target import select_method, parameter_types
from src.utils.java_parser import extract_dependencies
from scripts.analyze_focal_method_coverage import find_method_ranges, find_owned_method_ranges, load_focal_methods
from src.core.batch_runner import run_batch, load_method_list


SOURCE = """package p;
public class Outer {
    private static class Inner {
        private int addAll(int x, int y) {
            return x + y;
        }
    }
    private String ownField;
    public boolean addAll(java.util.Collection<String> values) {
        return values.isEmpty();
    }
}
"""


class FocalTargetTest(unittest.TestCase):
    def test_owner_excludes_nested_method_in_both_analysis_and_evaluation(self):
        self.assertEqual(2, len(find_method_ranges(SOURCE, "addAll")))
        ranges = find_owned_method_ranges(SOURCE, "addAll", "p.Outer", ["java.util.Collection"])
        self.assertEqual([(9, 11)], [(r.start, r.end) for r in ranges])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Outer.java"
            target.write_text(SOURCE, encoding="utf-8")
            result = extract_dependencies(str(target), "addAll", method_owner="p.Outer",
                                          method_parameter_types=["java.util.Collection"])
            self.assertEqual("boolean", result.return_type)
            self.assertEqual(["values"], [p["name"] for p in result.parameters])
            self.assertEqual(["ownField"], [f["name"] for f in result.field_dependencies])

    def test_wrong_signature_does_not_fall_back_to_nested_method(self):
        with self.assertRaisesRegex(ValueError, "found 0"):
            select_method(javalang.parse.parse(SOURCE), "addAll", "p.Outer", ["int", "int"])

    def test_binary_nested_class_owner_selects_only_its_method(self):
        _, method = select_method(javalang.parse.parse(SOURCE), "addAll", "p.Outer$Inner", ["int", "int"])
        self.assertEqual(["int", "int"], parameter_types(method))

    def test_overloaded_methods_require_parameter_types(self):
        source = "class A { int f(int x) { return x; } int f(String x) { return 0; } }"
        tree = javalang.parse.parse(source)
        with self.assertRaisesRegex(ValueError, "found 2"):
            select_method(tree, "f", "A")
        _, method = select_method(tree, "f", "A", ["String"])
        self.assertEqual(["String"], parameter_types(method))

    def test_strict_manifest_controls_evaluator_and_batch_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Outer.java"
            target.write_text(SOURCE, encoding="utf-8")
            item = {"id": "outer-add", "target": str(target), "method": "addAll",
                    "method_owner": "p.Outer", "method_parameter_types": ["java.util.Collection"]}
            manifest = root / "methods.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            focal = load_focal_methods(manifest, None, [])
            self.assertEqual([(9, 11)], [(r.start, r.end) for r in focal[0].ranges])
            with patch("src.core.batch_runner.Pipeline") as factory:
                factory.return_value.run.return_value.success = True
                factory.return_value.run.return_value.iterations = 1
                run_batch([item], str(root / "run"), {}, resume=False)
                self.assertEqual("p.Outer", factory.return_value.run.call_args.kwargs["method_owner"])

    def test_changed_frozen_source_is_rejected_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Outer.java"
            target.write_text(SOURCE, encoding="utf-8")
            manifest = root / "methods.json"
            manifest.write_text(json.dumps([{"id": "a", "target": str(target),
                                              "method": "addAll", "source_sha256": "0" * 64}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen source hash mismatch"):
                load_method_list(str(manifest))

    def test_direct_evaluation_entrypoint_can_import_strict_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Outer.java"
            target.write_text(SOURCE, encoding="utf-8")
            manifest = root / "methods.json"
            manifest.write_text(json.dumps([{"id": "a", "target": str(target), "method": "addAll",
                                              "method_owner": "p.Outer", "method_parameter_types": ["java.util.Collection"]}]), encoding="utf-8")
            script = Path(__file__).resolve().parents[1] / "scripts/analyze_focal_method_coverage.py"
            completed = subprocess.run([sys.executable, str(script), "--method-list", str(manifest),
                                        "--approach", f"Empty={root / 'empty'}", "--output-dir", str(root / "out")],
                                       cwd=root, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
