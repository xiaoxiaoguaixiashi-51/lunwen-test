import unittest
from scripts.summarize_request_costs import aggregate


class CostIndexTest(unittest.TestCase):
    def event(self, identity, **kwargs):
        return {"call_id": identity, "target_id": "t", "stage": "initial", "status": "ok",
                "provider_call_attempted": True, "sdk_max_retries": 0, "elapsed_seconds": 1,
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}, **kwargs}

    def test_blocked_is_not_billed_attempt_and_error_not_free(self):
        result = aggregate([self.event("a"), self.event("b", status="budget_blocked", provider_call_attempted=False, usage={}),
                            self.event("c", status="error", usage={})])
        self.assertEqual(3, result["totals"]["trace_events"])
        self.assertEqual(2, result["totals"]["provider_attempts"])
        self.assertEqual(1, result["totals"]["unknown_usage_attempts"])
        self.assertEqual(11, result["known_usage_totals"]["total_tokens"])
        self.assertFalse(result["full_usage_known"])

    def test_duplicate_rejected_and_legacy_inference_disclosed(self):
        with self.assertRaises(ValueError):
            aggregate([self.event("a"), self.event("a")])
        old = self.event("old")
        del old["provider_call_attempted"]
        self.assertEqual(1, aggregate([old])["legacy_events_with_inferred_attempt_flag"])

    def test_stages_separate_but_totals_include_all(self):
        result = aggregate([self.event("a"), self.event("b", stage="feedback")])
        self.assertEqual(2, len(result["by_target_stage"]))
        self.assertEqual(22, result["known_usage_totals"]["total_tokens"])
