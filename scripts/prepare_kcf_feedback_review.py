"""Create a fresh review bridge from audited feedback; retain every original outcome."""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.batch_runner import load_method_list
from src.utils.experiment_metadata import sha256_file
from scripts.run_stage_b_ours_full_feedback import validate_passing_seed_index, read_json, write_json


def classify_suite(row):
    counts = row.get("junit", {})
    if (row["final_status"] != "ok" or not row.get("integrity", {}).get("ok")
            or not isinstance(counts.get("tests_run"), int) or counts["tests_run"] <= 0
            or counts.get("failures") != 0):
        return "excluded"
    return "review" if row.get("semantic_review_required") else "accepted"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seed-xml-root", type=Path, required=True)
    parser.add_argument("--method-list", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Keep original scoring and review state")
    methods = {method["id"]: method for method in load_method_list(args.method_list)}
    validate_passing_seed_index(args.seed_xml_root, methods)
    base = read_json(args.seed_xml_root / "accepted_xml_index.json")
    rows = read_json(args.audit)["incremental_suites"]
    identities = [(row["round"], row["id"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate audited suite")
    # This review bridge is scoped to a single bounded round.
    if len({row["round"] for row in rows}) > 1:
        raise ValueError("Review one round at a time")
    for row in rows:
        if row["id"] not in methods:
            raise ValueError("Audited target is outside the frozen list")
        if classify_suite(row) != "excluded":
            source, xml = Path(row["final_source"]), Path(row["xml_file"])
            if not source.resolve().is_relative_to(args.run_dir.resolve()) or not xml.resolve().is_relative_to(args.run_dir.resolve()):
                raise ValueError("Suite evidence lies outside its run")
            if sha256_file(source) != row["final_source_sha256"] or sha256_file(xml) != row["xml_sha256"]:
                raise ValueError("Audited evidence changed")
    accepted = args.output_dir / "accepted_xml"
    pending = args.output_dir / "review_xml"
    accepted.mkdir(parents=True)
    pending.mkdir()
    for entry in base:
        shutil.copy2(args.seed_xml_root / entry["xml_name"], accepted / entry["xml_name"])
    review_index, excluded = [], []
    for row in rows:
        kind = classify_suite(row)
        if kind == "excluded":
            excluded.append({"id": row["id"], "status": row["final_status"], "junit": row["junit"]})
            continue
        name = f"round{row['round']}_{row['id']}.xml"
        if name in {entry["xml_name"] for entry in base}:
            raise ValueError("Incremental suite would replace an existing seed XML")
        entry = {"id": row["id"], "status": "ok", "xml_name": name, "xml_sha256": row["xml_sha256"],
                 "semantic_review_required": kind == "review", "repaired_source": row["final_source"],
                 "repaired_source_sha256": row["final_source_sha256"], "origin": "incremental_passing_suite"}
        shutil.copy2(row["xml_file"], (pending if kind == "review" else accepted) / name)
        (review_index if kind == "review" else base).append(entry)
    write_json(accepted / "accepted_xml_index.json", base)
    write_json(pending / "review_required_index.json", review_index)
    write_json(args.output_dir / "excluded_incremental_suites.json", excluded)
    validate_passing_seed_index(accepted, methods)
    print(json.dumps({"accepted_suites_before_review": len(base), "pending_review": len(review_index), "excluded_suites": len(excluded)}))


if __name__ == "__main__":
    main()
