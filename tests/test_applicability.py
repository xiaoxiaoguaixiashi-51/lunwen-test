import unittest

from src.retrieval.applicability import CONFLICT, SATISFIED, UNKNOWN, assess_record


class ApplicabilityTest(unittest.TestCase):
    def test_explicit_junit5_requirement_is_conflict_for_junit4_target(self):
        result = assess_record({"id": "x", "test_strategy": "Use JUnit 5 Jupiter extensions."})
        self.assertEqual(CONFLICT, result["status"])

    def test_negative_mention_of_forbidden_library_is_not_conflict(self):
        result = assess_record({"id": "x", "pitfalls": ["Do not use Mockito"]})
        self.assertEqual(UNKNOWN, result["status"])

    def test_matching_method_is_satisfied(self):
        result = assess_record({"id": "x", "method": "parse"}, target_method="parse")
        self.assertEqual(SATISFIED, result["status"])

    def test_cross_project_record_without_conflict_is_unknown(self):
        result = assess_record(
            {"id": "x", "project": "other", "class": "other.Type", "method": "parse"},
            target_project="target",
            target_class="target.Type",
            target_method="different",
        )
        self.assertEqual(UNKNOWN, result["status"])


if __name__ == "__main__":
    unittest.main()
