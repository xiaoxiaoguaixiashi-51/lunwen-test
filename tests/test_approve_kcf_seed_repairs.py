import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.approve_kcf_seed_repairs import validate_review


class ReviewGateTest(unittest.TestCase):
    def test_requires_matching_repaired_code_and_frozen_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Target.java"
            source.write_text("class Target {}\n", encoding="utf-8")
            repaired = root / "repaired.java.txt"
            repaired.write_text("class T {}", encoding="utf-8")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            code_hash = hashlib.sha256(repaired.read_bytes()).hexdigest()
            entry = {"repaired_source": str(repaired), "repaired_source_sha256": code_hash}
            method = {"target": str(source), "source_sha256": source_hash}
            review = {"decision": "approve", "reason": "Source-specific reasoning must be independently recorded here.",
                      "repaired_source_sha256": code_hash,
                      "source_evidence": [{"source": str(source), "sha256": source_hash, "line_start": 1, "line_end": 1}]}
            validate_review(review, entry, method)
            with self.assertRaises(ValueError):
                validate_review({**review, "source_evidence": []}, entry, method)
            repaired.write_text("changed after review", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_review(review, entry, method)
