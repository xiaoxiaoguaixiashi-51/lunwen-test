import unittest

from scripts.summarize_kcf_api_smoke import summarize_calls


class SmokeSummaryTest(unittest.TestCase):
    def test_unknown_usage_is_not_assumed_zero(self):
        result = summarize_calls([
            {"status": "ok", "response_model": "resolved", "elapsed_seconds": 2,
             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            {"status": "error", "elapsed_seconds": 1, "usage": {"total_tokens": None}},
        ])
        self.assertEqual(result["logical_calls"], 2)
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["usage"]["total_tokens"], {"known_sum": 15, "unknown_call_count": 1})
        self.assertEqual(result["returned_models"], ["resolved"])
        self.assertEqual(result["api_elapsed_seconds_sum"], 3)


if __name__ == "__main__":
    unittest.main()
