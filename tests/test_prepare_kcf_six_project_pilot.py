import json
import unittest
from pathlib import Path

from scripts.prepare_kcf_six_project_pilot import select_targets


class SixProjectPilotTest(unittest.TestCase):
    def test_uses_six_distinct_projects_and_preserves_frozen_metadata(self):
        rows = json.loads((Path(__file__).resolve().parents[1] / "experiments/method_lists/kcf_utg_rq1_methods_v2.json").read_text(encoding="utf-8"))
        selected = select_targets(rows)
        self.assertEqual(6, len({row["project_id"] for row in selected}))
        self.assertTrue(all(row in rows for row in selected))
        with self.assertRaises(ValueError):
            select_targets(rows + selected[:1])
