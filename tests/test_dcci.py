import unittest
from pathlib import Path

from src.metrics.dcci import score_method, score_method_list


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class DcciTest(unittest.TestCase):
    def test_scores_java_demo_as_dependency_complex(self):
        result = score_method(str(TARGET), "updateUserEmail")

        self.assertEqual("updateUserEmail", result["method"])
        self.assertGreater(result["dcci"], 1.0)
        self.assertGreater(result["dependency_summary"]["external_calls"], 3)
        self.assertTrue(result["dependency_summary"]["has_time_dependency"])

    def test_score_method_list_can_skip_errors(self):
        rows = score_method_list([{"id": "missing", "target": "missing.java", "method": "x"}], skip_errors=True)

        self.assertEqual(1, len(rows))
        self.assertIn("dcci_error", rows[0])


if __name__ == "__main__":
    unittest.main()
