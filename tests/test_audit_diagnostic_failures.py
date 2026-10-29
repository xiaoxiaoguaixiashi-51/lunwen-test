from pathlib import Path
import unittest
from scripts.audit_diagnostic_failures import audit


class FailureAuditTest(unittest.TestCase):
    def test_all_48_logs_are_accounted_for(self):
        root = Path(__file__).resolve().parents[1] / "results/knowledge_diagnostic_20261030"
        result = audit(root / "knowledge_diagnostic_generation_20261030.tgz",
                       root / "knowledge_diagnostic_reeval_20261030.tgz")
        self.assertEqual(48, len(result["rows"]))
        self.assertEqual(4, len(result["cases"]))
        self.assertEqual(0, result["api_calls"])
        self.assertTrue(all(case["units"] == 12 for case in result["cases"].values()))
        csv = next(case for name, case in result["cases"].items() if name.startswith("commons-csv"))
        self.assertEqual([12], list(csv["failing_tests_occurrences"].values()))
