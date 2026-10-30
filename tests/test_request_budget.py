import tempfile
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from src.utils.request_budget import RequestBudget, BudgetExceeded


class RequestBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "budget.sqlite"
        self.policy = {"max_calls_per_target": 2, "max_total_tokens_per_target": 100,
                       "max_input_tokens_per_call": 40, "max_output_tokens_per_call": 30}
        self.budget = RequestBudget(self.path, self.policy)

    def test_reopening_shares_cross_stage_call_limit(self):
        self.budget.reserve("a", "target", "initial", 20, 30)
        self.budget.settle("a", {"prompt_tokens": 20, "completion_tokens": 1})
        reopened = RequestBudget(self.path, self.policy)
        reopened.reserve("b", "target", "feedback", 20, 30)
        reopened.settle("b", {"prompt_tokens": 20, "completion_tokens": 1})
        with self.assertRaisesRegex(BudgetExceeded, "call budget"):
            reopened.reserve("c", "target", "repair", 20, 30)

    def test_unknown_charge_blocks_target_and_isolates_other_targets(self):
        self.budget.reserve("a", "first", "initial", 20, 30)
        self.budget.settle("a", {})
        with self.assertRaisesRegex(BudgetExceeded, "unresolved"):
            self.budget.reserve("b", "first", "feedback", 20, 30)
        self.budget.reserve("c", "second", "initial", 20, 30)

    def test_token_cap_reserves_worst_case(self):
        self.budget.reserve("a", "t", "initial", 40, 30)
        self.budget.settle("a", {"prompt_tokens": 40, "completion_tokens": 20})
        with self.assertRaisesRegex(BudgetExceeded, "token budget"):
            self.budget.reserve("b", "t", "feedback", 20, 30)

    def test_overrun_and_unsettled_reservations_fail_closed(self):
        self.budget.reserve("a", "t", "initial", 10, 30)
        with self.assertRaises(BudgetExceeded):
            self.budget.reserve("b", "t", "feedback", 10, 30)
        result = self.budget.settle("a", {"prompt_tokens": 11, "completion_tokens": 30})
        self.assertEqual("overrun", result["status"])
        with self.assertRaises(BudgetExceeded):
            self.budget.reserve("c", "t", "feedback", 10, 30)

    def test_policy_and_per_call_validation(self):
        with self.assertRaises(ValueError):
            RequestBudget(self.path, {**self.policy, "max_calls_per_target": 3})
        with self.assertRaises(ValueError):
            RequestBudget("relative.sqlite", self.policy)
        for target, incoming, outgoing in ((None, 10, 30), ("t", 41, 30), ("t", 10, 31)):
            with self.assertRaises(BudgetExceeded):
                self.budget.reserve("a", target, "initial", incoming, outgoing)

    def test_concurrent_reservations_cannot_overspend(self):
        def attempt(identity):
            budget = RequestBudget(self.path, self.policy)
            try:
                budget.reserve(identity, "shared", "initial", 10, 30)
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(1, sum(pool.map(attempt, ["one", "two"])))

    def test_inconsistent_usage_does_not_release_reserved_cost(self):
        self.budget.reserve("a", "t", "initial", 10, 30)
        result = self.budget.settle("a", {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 99})
        self.assertEqual("unknown", result["status"])
        self.assertEqual(40, result["charged_tokens"])
        with self.assertRaises(BudgetExceeded):
            self.budget.reserve("b", "t", "feedback", 10, 30)
