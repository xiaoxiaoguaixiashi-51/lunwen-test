import hashlib
import json
from pathlib import Path
import tarfile
import unittest


class SavedProbeReplayTest(unittest.TestCase):
    def test_frozen_real_round_evidence_and_snapshots(self):
        path = Path(__file__).resolve().parents[1] / "results/probe_round_scoring_20261030/probe_feedback_replay_v2_20261030.tgz"
        self.assertEqual("d05821dd0c02a00da8d9c0b17d54828b09f5711751095893c58f383283b9b6ef",
                         hashlib.sha256(path.read_bytes()).hexdigest())
        prefix = "probe_feedback_replay_v2_20261030/"
        with tarfile.open(path, "r:gz") as archive:
            summary = json.load(archive.extractfile(prefix + "round_replay_summary.json"))
            self.assertEqual(0, summary["api_calls"])
            self.assertEqual((39, 14), (summary["round0"]["focal_lines_covered"], summary["round0"]["focal_branches_covered"]))
            self.assertEqual((57, 29), (summary["round1"]["focal_lines_covered"], summary["round1"]["focal_branches_covered"]))
            for field in ("focal_lines_total", "focal_branches_total", "methods_total"):
                self.assertEqual(summary["round0"][field], summary["round1"][field])
            for number, count in ((0, 3), (1, 5)):
                folder = prefix + f"probe_union_round{number}/"
                content = archive.extractfile(folder + "accepted_xml_index_snapshot.json").read()
                manifest = json.load(archive.extractfile(folder + "execution_union_manifest.json"))
                self.assertEqual(hashlib.sha256(content).hexdigest(), manifest["accepted_index_sha256"])
                self.assertEqual(count, len(json.loads(content)))
                self.assertEqual(count, len(manifest["executions"]))
                self.assertTrue(all(r["junit"]["tests_run"] > 0 and r["junit"]["failures"] == 0 for r in manifest["executions"]))
