import json
import tempfile
import unittest
from pathlib import Path

from src.retrieval.dependency_knowledge import (
    knowledge_ids,
    load_knowledge_records,
    retrieve_dependency_knowledge,
)


class DependencyKnowledgeTest(unittest.TestCase):
    def test_load_knowledge_records_skips_blank_and_comment_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "knowledge.jsonl"
            path.write_text(
                "\n# comment\n" + json.dumps({"id": "one", "method": "createNumber"}) + "\n",
                encoding="utf-8",
            )

            records = load_knowledge_records(path)

            self.assertEqual(1, len(records))
            self.assertEqual("one", records[0]["id"])

    def test_retrieve_dependency_knowledge_ranks_matching_method(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "knowledge.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({
                            "id": "numberutils-create-number",
                            "class": "org.apache.commons.lang3.math.NumberUtils",
                            "method": "createNumber",
                            "problem": "numeric parsing suffix radix exception",
                        }),
                        json.dumps({
                            "id": "stringutils-overlay",
                            "class": "org.apache.commons.lang3.StringUtils",
                            "method": "overlay",
                            "problem": "string indexes",
                        }),
                    ]
                ),
                encoding="utf-8",
            )
            dependency_analysis = {
                "static_analysis": {
                    "class_name": "NumberUtils",
                    "method_name": "createNumber",
                    "external_calls": [],
                    "parameters": [{"name": "str", "type": "String"}],
                    "return_type": "Number",
                }
            }

            records = retrieve_dependency_knowledge(
                dependency_analysis,
                "class NumberUtils { public static Number createNumber(String str) { return null; } }",
                "createNumber",
                knowledge_path=path,
                max_examples=1,
            )

            self.assertEqual(["numberutils-create-number"], knowledge_ids(records))
            self.assertIn("retrieval_score", records[0])


if __name__ == "__main__":
    unittest.main()
