import csv
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.analyze_focal_method_coverage import (
    find_method_ranges,
    load_focal_methods,
    load_coverage_xmls,
    write_outputs,
    FocalMethod,
    MethodRange,
    LineCoverage,
    score_method,
)


class AnalyzeFocalMethodCoverageTest(unittest.TestCase):
    def test_missing_report_preserves_canonical_denominator(self):
        method = FocalMethod("m", "A.java", "f", "", "A", [MethodRange(3, 8)])
        reference = {"A": {3: LineCoverage(0, 2, 0), 5: LineCoverage(0, 0, 0)}}
        result = score_method(method, {}, reference)
        self.assertEqual((2, 0, 2, 0), (result["lines_total"], result["lines_covered"],
                                       result["branches_total"], result["branches_covered"]))
        self.assertEqual("0.0%", result["line_rate"])
        self.assertFalse(result["coverage_present"])

    def test_mismatched_instrumentation_is_rejected(self):
        method = FocalMethod("m", "A.java", "f", "", "A", [MethodRange(3, 8)])
        with self.assertRaisesRegex(ValueError, "Branch denominator mismatch"):
            score_method(method, {"A": {3: LineCoverage(1, 4, 2)}}, {"A": {3: LineCoverage(0, 2, 0)}})

    def test_missing_report_is_retained_as_a_feedback_gap(self):
        from scripts.run_stage_b_ours_full_feedback import read_detail
        method = FocalMethod("m", "A.java", "f", "", "A", [MethodRange(3, 8)])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_outputs([method], [("KCF", {})], root,
                          reference={"A": {3: LineCoverage(0, 2, 0)}})
            gaps = read_detail(root / "focal_method_coverage_detail.csv", "KCF")
            self.assertEqual(["m"], [row["id"] for row in gaps])

    def test_finds_java_method_range(self):
        source = textwrap.dedent(
            """
            package com.example;
            public class Demo {
                public int target(int x) {
                    if (x > 0) {
                        return x;
                    }
                    return 0;
                }
                public int other() {
                    return 1;
                }
            }
            """
        ).strip()

        ranges = find_method_ranges(source, "target")

        self.assertEqual(1, len(ranges))
        self.assertEqual(3, ranges[0].start)
        self.assertEqual(8, ranges[0].end)

    def test_scores_focal_lines_from_cobertura_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "src" / "com" / "example" / "Demo.java"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                textwrap.dedent(
                    """
                    package com.example;
                    public class Demo {
                        public int target(int x) {
                            if (x > 0) {
                                return x;
                            }
                            return 0;
                        }
                    }
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            method_list = root / "methods.json"
            method_list.write_text(
                json.dumps(
                    [
                        {
                            "id": "demo-target",
                            "target": str(source_path),
                            "method": "target",
                            "dcci": 1.25,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            xml_root = root / "xml"
            xml_root.mkdir()
            (xml_root / "coverage.xml").write_text(
                textwrap.dedent(
                    """
                    <coverage>
                      <packages><package name="com.example"><classes>
                        <class name="com.example.Demo" filename="com/example/Demo.java">
                          <lines>
                            <line number="3" hits="1"/>
                            <line number="4" hits="1" branch="true" condition-coverage="50% (1/2)"/>
                            <line number="5" hits="0"/>
                            <line number="7" hits="1"/>
                          </lines>
                        </class>
                      </classes></package></packages>
                    </coverage>
                    """
                ).strip(),
                encoding="utf-8",
            )

            focal_methods = load_focal_methods(method_list, None, [])
            coverage = load_coverage_xmls(xml_root)
            output_dir = root / "out"
            write_outputs(focal_methods, [("DemoApproach", coverage)], output_dir)

            with (output_dir / "focal_method_coverage_summary.csv").open(encoding="utf-8", newline="") as handle:
                summary = next(csv.DictReader(handle))
            with (output_dir / "focal_method_coverage_detail.csv").open(encoding="utf-8", newline="") as handle:
                detail = next(csv.DictReader(handle))

            self.assertEqual("4", summary["focal_lines_total"])
            self.assertEqual("3", summary["focal_lines_covered"])
            self.assertEqual("75.0%", summary["focal_line_rate"])
            self.assertEqual("2", summary["focal_branches_total"])
            self.assertEqual("1", summary["focal_branches_covered"])
            self.assertEqual("1", detail["method_match_count"])

    def test_scores_focal_lines_from_jacoco_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "src" / "com" / "example" / "Demo.java"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                textwrap.dedent(
                    """
                    package com.example;
                    public class Demo {
                        public int target(int x) {
                            if (x > 0) {
                                return x;
                            }
                            return 0;
                        }
                    }
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            method_list = root / "methods.json"
            method_list.write_text(
                json.dumps(
                    [
                        {
                            "id": "demo-target",
                            "target": str(source_path),
                            "method": "target",
                            "dcci": 1.25,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            xml_root = root / "xml"
            xml_root.mkdir()
            (xml_root / "jacoco.xml").write_text(
                textwrap.dedent(
                    """
                    <report name="demo">
                      <package name="com/example">
                        <sourcefile name="Demo.java">
                          <line nr="3" mi="0" ci="1" mb="0" cb="0"/>
                          <line nr="4" mi="0" ci="1" mb="1" cb="1"/>
                          <line nr="5" mi="1" ci="0" mb="0" cb="0"/>
                          <line nr="7" mi="0" ci="1" mb="0" cb="0"/>
                        </sourcefile>
                      </package>
                    </report>
                    """
                ).strip(),
                encoding="utf-8",
            )

            focal_methods = load_focal_methods(method_list, None, [])
            coverage = load_coverage_xmls(xml_root)
            output_dir = root / "out"
            write_outputs(focal_methods, [("JaCoCo", coverage)], output_dir)

            with (output_dir / "focal_method_coverage_summary.csv").open(encoding="utf-8", newline="") as handle:
                summary = next(csv.DictReader(handle))

            self.assertEqual("4", summary["focal_lines_total"])
            self.assertEqual("3", summary["focal_lines_covered"])
            self.assertEqual("75.0%", summary["focal_line_rate"])
            self.assertEqual("2", summary["focal_branches_total"])
            self.assertEqual("1", summary["focal_branches_covered"])


if __name__ == "__main__":
    unittest.main()
