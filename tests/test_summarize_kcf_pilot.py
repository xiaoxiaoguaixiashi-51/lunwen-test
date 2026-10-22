import unittest

from scripts.summarize_kcf_pilot import select_status_rows, junit_counts


class PilotJoinTest(unittest.TestCase):
    def test_missing_continuation_does_not_replace_existing_test_failure(self):
        first = [{"id": "a", "status": "test_failed"}, {"id": "b", "status": "missing_status"}]
        later = [{"id": "a", "status": "missing_status"}, {"id": "b", "status": "ok"}]
        result = select_status_rows([first, later])
        self.assertEqual("test_failed", result["a"]["status"])
        self.assertEqual("ok", result["b"]["status"])

    def test_junit_failure_is_not_a_pass_and_unknown_is_not_zero(self):
        self.assertEqual({"tests_run": 12, "failures": 0}, junit_counts("OK (12 tests)"))
        self.assertEqual({"tests_run": 16, "failures": 1}, junit_counts("Tests run: 16,  Failures: 1"))
        self.assertEqual({"tests_run": None, "failures": None}, junit_counts(""))
