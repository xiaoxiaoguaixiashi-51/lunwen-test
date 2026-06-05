import unittest
from pathlib import Path

from src.utils.java_parser import extract_dependencies


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "examples" / "java-demo" / "src" / "main" / "java" / "com" / "example" / "service" / "UserService.java"


class JavaParserTest(unittest.TestCase):
    def test_extracts_update_user_email_dependencies(self):
        info = extract_dependencies(str(TARGET), "updateUserEmail")
        data = info.to_dict()

        self.assertEqual("UserService", data["class_name"])
        self.assertEqual("updateUserEmail", data["method_name"])
        self.assertEqual("User", data["return_type"])
        self.assertIn({"name": "userId", "type": "Long"}, data["parameters"])
        self.assertIn({"name": "newEmail", "type": "String"}, data["parameters"])
        self.assertTrue(data["has_time_dependency"])

        constructor_types = {item["type"] for item in data["constructor_params"]}
        self.assertIn("UserRepository", constructor_types)
        self.assertIn("CacheManager", constructor_types)
        self.assertIn("EventPublisher", constructor_types)

        calls = {(item["target"], item["method"]) for item in data["external_calls"]}
        self.assertIn(("userRepository", "findById"), calls)
        self.assertIn(("cacheManager", "evict"), calls)
        self.assertIn(("eventPublisher", "publish"), calls)

    def test_raises_for_missing_method(self):
        with self.assertRaises(ValueError):
            extract_dependencies(str(TARGET), "missingMethod")


if __name__ == "__main__":
    unittest.main()
