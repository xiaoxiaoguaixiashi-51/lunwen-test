import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_knowledge_diagnostic import prepare, tfidf_rank, fixed_ids


class DiagnosticPreviewTest(unittest.TestCase):
    def test_tfidf_zero_and_tie(self):
        rows = [{"id": "b", "problem": "reflection"}, {"id": "a", "problem": "reflection"}]
        self.assertEqual([], tfidf_rank(rows, "unseenword"))
        self.assertEqual(["a", "b"], [r["id"] for r in tfidf_rank(rows, "reflection")])

    def test_fixed_selection_independent_of_input_order(self):
        rows = [{"id": str(i)} for i in range(12)]
        self.assertEqual(fixed_ids(rows), fixed_ids(list(reversed(rows))))

    def test_real_preview_offline_and_common_inputs(self):
        root = Path(__file__).resolve().parents[1]
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            manifest, previews = prepare(
                root / "results/seed_failure_repair_20261022/seed_failure_repair_20261022.tgz",
                root / "experiments/knowledge/dependency_construction_knowledge.jsonl",
                root / "scripts/run_stage_b_ours_full_feedback.py")
        self.assertEqual(48, len(previews))
        self.assertEqual(0, manifest["api_calls"])
        self.assertFalse(manifest["executable"])
        groups = {}
        for row in manifest["units"]:
            groups.setdefault((row["case_id"], row["repeat"]), []).append(row)
            self.assertFalse(row["executable"])
            content = previews[row["unit_id"]]["messages"][1]["content"]
            self.assertNotIn('"retrieval_score":', content)
            if row["arm"] == "N":
                self.assertEqual([], row["selection"])
        self.assertEqual(12, len(groups))
        for rows in groups.values():
            self.assertEqual(set("NFLT"), {r["arm"] for r in rows})
            self.assertEqual([1, 2, 3, 4], [r["position_in_block"] for r in rows])
            for field in ("original_sha256", "failure_sha256", "saved_context_sha256", "query_sha256"):
                self.assertEqual(1, len({r[field] for r in rows}))

    def test_reject_changed_input(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            prepare(Path(__file__), Path(__file__), Path(__file__))


if __name__ == "__main__":
    unittest.main()
