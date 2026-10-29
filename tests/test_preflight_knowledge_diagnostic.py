import unittest
from scripts.preflight_knowledge_diagnostic import budget_check


class BudgetTest(unittest.TestCase):
    def test_input_reserve_and_knowledge_boundaries(self):
        self.assertTrue(budget_check(11744, 2048))
        self.assertFalse(budget_check(11745, 2048))
        self.assertFalse(budget_check(100, 2049))
