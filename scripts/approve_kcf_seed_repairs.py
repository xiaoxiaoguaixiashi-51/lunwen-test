"""Apply explicit source-grounded review decisions to a fresh passing XML seed set."""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_stage_b_ours_full_feedback import validate_passing_seed_index, read_json, write_json
from src.core.batch_runner import load_method_list
from src.utils.experiment_metadata import sha256_file


def validate_review(decision, entry, method):
    if decision["decision"] != "approve" or len(decision.get("reason", "")) < 30:
        raise ValueError("Explicit source-grounded approval reason is required")
    expected = entry["repaired_source_sha256"]
    if decision.get("repaired_source_sha256") != expected or sha256_file(entry["repaired_source"]) != expected:
        raise ValueError("Reviewed repaired source hash mismatch")
    evidence = decision.get("source_evidence", [])
    if not evidence:
        raise ValueError("Approval needs frozen focal source evidence")
    for item in evidence:
        if Path(item["source"]).resolve() != Path(method["target"]).resolve():
            raise ValueError("Evidence is not the frozen focal source")
        if item.get("sha256") != method.get("source_sha256") or sha256_file(item["source"]) != item["sha256"]:
            raise ValueError("Source evidence hash mismatch")
        count = len(Path(item["source"]).read_text(encoding="utf-8").splitlines())
        if not 1 <= item["line_start"] <= item["line_end"] <= count:
            raise ValueError("Invalid evidence line range")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--method-list", required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Keep original evidence; use a new accepted XML directory")
    methods = {method["id"]: method for method in load_method_list(args.method_list)}
    initial = args.repair_root / "accepted_xml"
    validate_passing_seed_index(initial, methods)
    entries = read_json(initial / "accepted_xml_index.json")
    pending = {entry["id"]: entry for entry in read_json(args.repair_root / "review_xml/review_required_index.json")}
    decisions = read_json(args.reviews)
    ids = [decision["id"] for decision in decisions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate review decisions")
    approved = []
    for decision in decisions:
        if decision["decision"] != "approve":
            continue
        entry = pending[decision["id"]]
        if Path(entry["xml_name"]).name != entry["xml_name"]:
            raise ValueError("Invalid reviewed XML filename")
        validate_review(decision, entry, methods[decision["id"]])
        if sha256_file(args.repair_root / "review_xml" / entry["xml_name"]) != entry["xml_sha256"]:
            raise ValueError("Reviewed XML hash mismatch")
        approved.append(entry)
    args.output_dir.mkdir(parents=True)
    for entry in entries:
        shutil.copy2(initial / entry["xml_name"], args.output_dir / entry["xml_name"])
    for entry in approved:
        if entry["xml_name"] in {item["xml_name"] for item in entries}:
            raise ValueError("Review would replace an accepted XML entry")
        shutil.copy2(args.repair_root / "review_xml" / entry["xml_name"], args.output_dir / entry["xml_name"])
        entries.append({**entry, "semantic_review_required": False, "origin": "explicit_source_grounded_review"})
    shutil.copy2(args.reviews, args.output_dir / "semantic_reviews.json")
    write_json(args.output_dir / "accepted_xml_index.json", entries)
    validate_passing_seed_index(args.output_dir, methods)
    print(json.dumps({"accepted_suites": len(entries), "newly_approved_repairs": len(approved)}))


if __name__ == "__main__":
    main()
