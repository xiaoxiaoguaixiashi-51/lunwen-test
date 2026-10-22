import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.audit_kcf_saved_retrieval import audit, rank


class SavedRetrievalAuditTest(unittest.TestCase):
    def test_positive_only_and_stable_ties(self):
        records = [{"id": "b", "problem": "visibility"}, {"id": "a", "problem": "visibility"}]
        self.assertEqual(["a", "b"], [row["id"] for row in rank(records, "visibility")])
        self.assertEqual([], rank(records, "unrelated"))

    def test_saved_replay_must_match_ids_and_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge = root / "kb.jsonl"
            records = [{"id": name, "problem": "visibility"} for name in ("a", "b", "c")]
            knowledge.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
            seed = {"status": "test_failed", "method": {"id": "t", "project_id": "p", "fqcn": "p.T", "method": "f"}}
            for corrupt in (False, True):
                archive = root / ("bad.tgz" if corrupt else "ok.tgz")
                saved = [{"id": name, "retrieval_score": 2 if corrupt else 1} for name in ("a", "b", "c")]
                files = {"r/seed_input_index.json": json.dumps([seed]),
                         "r/cases/t/original.java.txt": "visibility",
                         "r/cases/t/original_failure.log": "visibility",
                         "r/cases/t/retrieval.json": json.dumps(saved),
                         "r/cases/t/status.json": json.dumps({"status": "test_failed"})}
                with tarfile.open(archive, "w:gz") as handle:
                    for name, content in files.items():
                        data = content.encode()
                        member = tarfile.TarInfo(name)
                        member.size = len(data)
                        handle.addfile(member, io.BytesIO(data))
                if corrupt:
                    with self.assertRaisesRegex(ValueError, "replay mismatch"):
                        audit(archive, knowledge)
                else:
                    result = audit(archive, knowledge)
                    self.assertEqual(0, result["api_calls"])
                    self.assertEqual(1, result["failed_seed_cases_total"])
                    self.assertTrue(result["cases"][0]["replay_exact_match"])


if __name__ == "__main__":
    unittest.main()
