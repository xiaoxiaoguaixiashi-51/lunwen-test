import unittest
from pathlib import Path
from scripts.summarize_knowledge_diagnostic import summarize


class DiagnosticSummaryTest(unittest.TestCase):
    def test_real_archives_and_corrected_evaluation(self):
        root = Path(__file__).resolve().parents[1] / "results/knowledge_diagnostic_20261030"
        result = summarize(root / "knowledge_diagnostic_generation_20261030.tgz",
                           root / "knowledge_diagnostic_reeval_20261030.tgz")
        self.assertEqual(48, result["recorded_api_calls"])
        self.assertEqual(0, result["requests_over_input_limit"])
        self.assertEqual(12, result["passing_suites_pending_semantic_review"])
        self.assertEqual(470026, result["usage"]["total_tokens"])
        self.assertEqual(1, len({str(result["by_arm"][arm]) for arm in "NFLT"}))

    def test_changed_archive_rejected(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            summarize(Path(__file__), Path(__file__))
