import unittest
from scripts.run_knowledge_diagnostic import validate_plan


class PlanValidationTest(unittest.TestCase):
    def fixture(self):
        units = [{"unit_id": str(i), "prompt_sha256": str(i)} for i in range(48)]
        return {"units": units}, {"budget_rows": [{**r, "within_estimated_budget": True} for r in units],
                                  "blocked_entire_cases": [], "all_estimated_budgets_pass": True}

    def test_valid_and_modified_prompt(self):
        plan, preflight = self.fixture()
        validate_plan(plan, preflight)
        plan["units"][0]["prompt_sha256"] = "changed"
        with self.assertRaises(ValueError):
            validate_plan(plan, preflight)

    def test_blocked_or_duplicate_preflight_rejected(self):
        plan, preflight = self.fixture()
        preflight["blocked_entire_cases"] = ["case"]
        with self.assertRaises(ValueError):
            validate_plan(plan, preflight)
        preflight["blocked_entire_cases"] = []
        preflight["budget_rows"][1] = preflight["budget_rows"][0]
        with self.assertRaises(ValueError):
            validate_plan(plan, preflight)
