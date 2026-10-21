import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts.run_stage_b_ours_full_feedback import (
    generate_incremental_test,
    repair_test,
)


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs))
        return """```java
public class GeneratedTest {
}
```"""


class StageBOursFullFeedbackAblationTest(unittest.TestCase):
    def _method_and_row(self, source_file: Path):
        method = {
            "id": "demo-method",
            "project_id": "demo",
            "fqcn": "org.example.Demo",
            "method": "work",
            "target": str(source_file),
            "package": "org.example",
        }
        row = {
            "id": "demo-method",
            "line_ranges": "1-4",
            "Ours_Full_lines_covered": "1",
            "Ours_Full_lines_total": "4",
            "Ours_Full_line_rate": "25.0%",
            "Ours_Full_branches_covered": "0",
            "Ours_Full_branches_total": "2",
            "Ours_Full_branch_rate": "0.0%",
        }
        return method, row

    def _args(self, **overrides):
        values = {
            "approach_name": "Ours_Full",
            "max_knowledge_examples": 3,
            "max_tokens": 1024,
            "disable_coverage_gap_retrieval": False,
            "disable_failure_repair_retrieval": False,
            "disable_static_guard": False,
        }
        values.update(overrides)
        return Namespace(**values)

    def test_coverage_gap_retrieval_can_be_disabled_for_a1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "Demo.java"
            source.write_text("package org.example;\nclass Demo { int work() { return 1; } }\n", encoding="utf-8")
            method, row = self._method_and_row(source)
            llm = RecordingLLM()

            with patch("scripts.run_stage_b_ours_full_feedback.retrieve_for_text") as retrieve:
                test_code, retrieved = generate_incremental_test(
                    llm,
                    method,
                    row,
                    1,
                    [{"id": "record"}],
                    self._args(disable_coverage_gap_retrieval=True),
                )

            retrieve.assert_not_called()
            self.assertEqual([], retrieved)
            self.assertIn("package org.example;", test_code)

    def test_failure_repair_retrieval_can_be_disabled_for_a1(self):
        llm = RecordingLLM()
        method = {
            "fqcn": "org.example.Demo",
            "method": "work",
            "package": "org.example",
        }

        with patch("scripts.run_stage_b_ours_full_feedback.retrieve_for_text") as retrieve:
            repaired, retrieved = repair_test(
                llm,
                "public class GeneratedTest {}",
                method,
                "compile failed",
                "compile_failed",
                [{"id": "record"}],
                self._args(disable_failure_repair_retrieval=True),
            )

        retrieve.assert_not_called()
        self.assertEqual([], retrieved)
        self.assertIn("package org.example;", repaired)

    def test_default_full_still_uses_retrieval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "Demo.java"
            source.write_text("package org.example;\nclass Demo { int work() { return 1; } }\n", encoding="utf-8")
            method, row = self._method_and_row(source)
            llm = RecordingLLM()

            with patch(
                "scripts.run_stage_b_ours_full_feedback.retrieve_for_text",
                return_value=[{"id": "record"}],
            ) as retrieve:
                _test_code, retrieved = generate_incremental_test(
                    llm,
                    method,
                    row,
                    1,
                    [{"id": "record"}],
                    self._args(),
                )

            retrieve.assert_called_once()
            self.assertEqual([{"id": "record"}], retrieved)

    def test_static_guard_can_be_disabled_for_coverage_feedback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "Demo.java"
            source.write_text("package org.example;\nclass Demo { int work() { return 1; } }\n", encoding="utf-8")
            method, row = self._method_and_row(source)
            llm = RecordingLLM()

            test_code, _retrieved = generate_incremental_test(
                llm,
                method,
                row,
                1,
                [],
                self._args(disable_static_guard=True),
            )

            system_prompt, user_prompt, _ = llm.calls[0]
            self.assertNotIn("JUnit 4 only", system_prompt)
            self.assertNotIn("Do not use Mockito", system_prompt)
            self.assertNotIn("JUnit 4 test class named", user_prompt)
            self.assertNotIn("package org.example;", test_code)


if __name__ == "__main__":
    unittest.main()
