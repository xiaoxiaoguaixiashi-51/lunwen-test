import unittest

from scripts.normalize_focal_coverage_denominator import normalize


def row(method_id, prefix, total, covered, rate):
    return {
        "id": method_id,
        "target": f"{method_id}.java",
        "method": "run",
        "line_ranges": "1-10",
        f"{prefix}_lines_total": str(total),
        f"{prefix}_lines_covered": str(covered),
        f"{prefix}_line_rate": rate,
        f"{prefix}_branches_total": "2",
        f"{prefix}_branches_covered": str(min(covered, 2)),
        f"{prefix}_branch_rate": "100%" if covered >= 2 else "0%",
    }


class NormalizeFocalCoverageTest(unittest.TestCase):
    def test_missing_candidate_coverage_uses_reference_denominator_and_zero_hits(self):
        reference = {
            "a": row("a", "FULL", 10, 8, "80%"),
            "b": row("b", "FULL", 5, 4, "80%"),
        }
        candidate = {
            "a": row("a", "A1", 10, 6, "60%"),
            "b": {
                "id": "b",
                "target": "b.java",
                "method": "run",
                "line_ranges": "1-10",
                "A1_lines_total": "0",
                "A1_lines_covered": "0",
                "A1_line_rate": "",
                "A1_branches_total": "0",
                "A1_branches_covered": "0",
                "A1_branch_rate": "",
            },
        }

        result = normalize(reference, candidate, "FULL", "A1")

        self.assertEqual(2, result["methods_total"])
        self.assertEqual(1, result["methods_with_coverage_data"])
        self.assertEqual(["b"], result["methods_missing_coverage"])
        self.assertEqual(15, result["lines_total"])
        self.assertEqual(6, result["lines_covered"])
        self.assertEqual(4, result["branches_total"])
        self.assertEqual(2, result["branches_covered"])
        self.assertEqual(40.0, result["line_rate"] * 100)

    def test_rejects_mismatched_method_sets(self):
        with self.assertRaisesRegex(ValueError, "Method list mismatch"):
            normalize({"a": row("a", "FULL", 10, 8, "80%")}, {}, "FULL", "A1")


if __name__ == "__main__":
    unittest.main()
