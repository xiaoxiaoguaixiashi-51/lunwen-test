import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from scripts.summarize_phase_costs import aggregate
from src.core.llm_client import trace_target
from src.utils.phase_trace import phase, measured


class PhaseTraceTest(unittest.TestCase):
    def test_nested_exception_incomplete_and_duplicate_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phase.jsonl"
            with patch.dict(os.environ, {"KCF_PHASE_TRACE_PATH": str(path), "KCF_EXPERIMENT_STAGE": "test"}):
                with trace_target("method1"), phase("outer"):
                    with self.assertRaises(ValueError):
                        with phase("child"):
                            raise ValueError("secret-sentinel-must-not-appear")
                with phase("evosuite", target_id="project::Class"):
                    pass
            content = path.read_text()
            self.assertNotIn("secret-sentinel", content)
            events = [json.loads(line) for line in content.splitlines()]
            summary = aggregate(events)
            self.assertEqual(0, summary["incomplete_spans"])
            child = next(row for row in summary["by_target_stage_phase"] if row["phase"] == "child")
            self.assertEqual("method1", child["target_id"])
            self.assertEqual(1, child["exceptions"])
            root_ends = [event for event in events if event["event"] == "end" and event["parent_span_id"] is None]
            self.assertEqual(sum(event["elapsed_seconds"] for event in root_ends), summary["sum_completed_root_seconds"])
            self.assertFalse(summary["full_compute_cost_known"])
            with self.assertRaises(ValueError):
                aggregate(events + events)
            incomplete = aggregate([event for event in events if not (event["event"] == "end" and event["phase"] == "child")])
            self.assertEqual(1, incomplete["incomplete_spans"])
            with self.assertRaises(ValueError):
                aggregate([event for event in events if event["phase"] != "outer"])

    def test_instrumentation_disabled_preserves_return_and_exception(self):
        @measured("sample")
        def sample(number):
            if number < 0:
                raise RuntimeError("expected")
            return number + 1
        with patch.dict(os.environ, {"KCF_PHASE_TRACE_PATH": ""}):
            self.assertEqual(3, sample(2))
            with self.assertRaises(RuntimeError):
                sample(-1)

    def test_real_pipeline_and_independent_rag_with_fake_provider(self):
        from tests.test_pipeline_offline import FakeLLMClient, FakeCompiler, TARGET
        from tests.test_rag_llm_baseline_runner import RecordingLLM
        from src.core.pipeline import Pipeline
        from src.core.rag_llm_baseline_runner import RagLlmBaselineRunner
        keep = os.environ.get("KCF_PHASE_SMOKE_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=False)
        with (nullcontext(keep) if keep else tempfile.TemporaryDirectory()) as directory:
            root = Path(directory)
            path = root / "phase.jsonl"
            with patch.dict(os.environ, {"KCF_PHASE_TRACE_PATH": str(path), "KCF_EXPERIMENT_STAGE": "offline",
                                       "LUNWEN_ENABLE_JAVA6_GUARD": "0"}), patch(
                                           "socket.socket", side_effect=AssertionError("network prohibited")):
                pipeline = Pipeline(config={"retrieval": {"enabled": True}},
                                    llm_client=FakeLLMClient(), compiler=FakeCompiler())
                with trace_target("kcf-method"):
                    result = pipeline.run(str(TARGET), "updateUserEmail")
                self.assertTrue(result.success)
                with trace_target("rag-method"):
                    RagLlmBaselineRunner(llm_client=RecordingLLM()).run_one(str(TARGET), "updateUserEmail", str(root / "rag"))
            events = [json.loads(line) for line in path.read_text().splitlines()]
            summary = aggregate(events)
            phases = {event["phase"] for event in events}
            self.assertTrue({"kcf_initial_pipeline", "task_analysis", "initial_knowledge_retrieval", "test_planning",
                             "initial_code_generation", "initial_compile_and_repair", "initial_code_repair",
                             "rag_initial_generation", "rag_source_retrieval"} <= phases)
            self.assertEqual(0, summary["incomplete_spans"])
            self.assertEqual({"kcf-method", "rag-method"}, {event["target_id"] for event in events})
            if keep:
                summary["fixture_kind"] = "fake_provider_and_compiler_instrumentation_smoke"
                summary["real_api_calls"] = 0
                (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
