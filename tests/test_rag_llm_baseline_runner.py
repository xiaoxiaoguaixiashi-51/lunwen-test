import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.rag_llm_baseline_runner import (
    RagLlmBaselineRunner,
    ensure_java6_guard_disabled,
    load_method_list,
    retrieve_source_context,
    run_batch,
)


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs))
        return """```java
package org.example;

import org.junit.Test;
import static org.junit.Assert.*;

public class ExampleTest {
    @Test
    public void test_value() {
        assertEquals(1, 1);
    }
}
```"""


class RagLlmBaselineRunnerTest(unittest.TestCase):
    def test_refuses_to_run_with_java6_guard_enabled(self):
        with patch.dict("os.environ", {"LUNWEN_ENABLE_JAVA6_GUARD": "1"}):
            with self.assertRaises(RuntimeError):
                ensure_java6_guard_disabled()

    def test_load_method_list_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "methods.json"
            path.write_text(json.dumps([{"id": "one", "target": "A.java"}]), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_method_list(str(path))

    def test_retrieve_source_context_keeps_target_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "src" / "main" / "java" / "org" / "example"
            root.mkdir(parents=True)
            target = root / "Example.java"
            helper = root / "Helper.java"
            target.write_text(
                "package org.example; public class Example { public int value() { return Helper.answer(); } }",
                encoding="utf-8",
            )
            helper.write_text(
                "package org.example; public class Helper { public static int answer() { return 1; } }",
                encoding="utf-8",
            )

            files = retrieve_source_context(target, "value", max_files=2, max_chars=10000)

            self.assertEqual(target, files[0].path)
            self.assertEqual(helper, files[1].path)

    def test_run_one_saves_generated_test_and_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "src" / "main" / "java" / "org" / "example"
            source_root.mkdir(parents=True)
            target = source_root / "Example.java"
            target.write_text("package org.example; public class Example { public int value() { return 1; } }", encoding="utf-8")
            output = root / "run" / "example_value"

            llm = RecordingLLM()
            runner = RagLlmBaselineRunner(llm_client=llm, max_context_files=1)
            result = runner.run_one(str(target), "value", str(output))

            self.assertTrue(result.success)
            self.assertTrue((output / "ExampleTest.java").exists())
            self.assertTrue((output / "value_rag_llm_report.json").exists())
            system_prompt, user_prompt, _ = llm.calls[0]
            self.assertIn("RAG+LLM baseline", system_prompt)
            self.assertIn("Retrieved Source Context", user_prompt)
            self.assertNotIn("Java 6 source-compatible", system_prompt)

    def test_run_batch_writes_summary_without_pipeline_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "src" / "main" / "java" / "org" / "example"
            source_root.mkdir(parents=True)
            target = source_root / "Example.java"
            target.write_text("package org.example; public class Example { public int value() { return 1; } }", encoding="utf-8")
            output = root / "baseline_run"

            runner = RagLlmBaselineRunner(llm_client=RecordingLLM(), max_context_files=1)
            summary = run_batch(
                [{"id": "example_value", "target": str(target), "method": "value"}],
                str(output),
                runner,
            )

            self.assertEqual("rag_llm", summary["baseline"])
            self.assertEqual(1, summary["completed"])
            status = json.loads((output / "example_value" / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("rag_llm", status["baseline"])
            self.assertNotIn("iterations", status)


if __name__ == "__main__":
    unittest.main()
