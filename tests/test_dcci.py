import unittest
from pathlib import Path

from src.metrics.dcci import score_method


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class DcciTest(unittest.TestCase):
    def test_scores_java_demo_as_dependency_complex(self):
        result = score_method(str(TARGET), "updateUserEmail")

        self.assertEqual("updateUserEmail", result["method"])
        self.assertGreater(result["dcci"], 1.0)
        self.assertGreater(result["dependency_summary"]["external_calls"], 3)
        self.assertTrue(result["dependency_summary"]["has_time_dependency"])


if __name__ == "__main__":
    unittest.main()
