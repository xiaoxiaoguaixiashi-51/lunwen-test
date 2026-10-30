"""Replay already accepted seed/incremental probes through per-round scoring. Zero API."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import probe_union_feedback as probe
from scripts.build_kcf_coverage_reference import digest
from scripts.merge_kcf_execution_coverage import resolve_executions
from scripts.run_stage_b_ours_full_feedback import read_detail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--seed-root", type=Path, required=True)
    parser.add_argument("--reviewed-final-root", type=Path, required=True)
    parser.add_argument("--execution-roots", nargs="+", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--jacoco-cli", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError("Preserve original scores; use fresh replay output")
    items = json.loads(args.method_list.read_text(encoding="utf-8"))
    methods = {m["id"]: m for m in items}
    seed_entries = json.loads((args.seed_root / "accepted_xml_index.json").read_text(encoding="utf-8"))
    final_entries = json.loads((args.reviewed_final_root / "accepted_xml_index.json").read_text(encoding="utf-8"))
    seed_pairs = {(e["id"], e["xml_name"], e["xml_sha256"]) for e in seed_entries}
    final_pairs = {(e["id"], e["xml_name"], e["xml_sha256"]) for e in final_entries}
    if not seed_pairs <= final_pairs:
        raise ValueError("Final acceptance removed/changed prior seeds")
    original_records = resolve_executions(args.reviewed_final_root, methods, args.execution_roots)
    by_name = {r["accepted_xml_name"]: r for r in original_records}
    scoring_args = SimpleNamespace(exact_exec_union=True, passing_only=True, exact_reference_root=str(args.reference_root),
                                   reference_xml_root=str(args.reference_root / "xml"),
                                   seed_execution_roots=[str(p) for p in args.execution_roots],
                                   projects_root=str(args.projects_root), jacoco_cli=str(args.jacoco_cli), approach_name="KCF_UTG_REPLAY")
    probe.validate_exact_mode(scoring_args)
    output.mkdir(parents=True)
    probe.prepare_seed_index(args.seed_root, output / "probe_accepted_xml", methods, args.execution_roots)
    started = time.monotonic()
    first = probe.evaluate_round(scoring_args, output, args.method_list, 0)[0]
    first_seconds = time.monotonic() - started
    added = []
    for entry in final_entries:
        if (entry["id"], entry["xml_name"], entry["xml_sha256"]) in seed_pairs:
            continue
        record = by_name[entry["xml_name"]]
        probe.accept_incremental(output / "probe_accepted_xml", {
            "status": entry["status"], "semantic_review_required": entry["semantic_review_required"],
            "xml_file": record["xml_file"], "acceptance_origin": entry["origin"]}, entry["id"], 1)
        added.append(entry)
    started = time.monotonic()
    second = probe.evaluate_round(scoring_args, output, args.method_list, 1)[0]
    second_seconds = time.monotonic() - started
    for field in ("focal_lines_total", "focal_branches_total", "methods_total"):
        if first[field] != second[field]:
            raise ValueError("Round denominator changed")
    summary = {"kind": "offline_existing_accepted_suites_round_replay_not_new_generation", "api_calls": 0,
               "method_list_sha256": digest(args.method_list), "seed_index_sha256": digest(args.seed_root / "accepted_xml_index.json"),
               "reviewed_index_sha256": digest(args.reviewed_final_root / "accepted_xml_index.json"),
               "round0": first, "round1": second, "newly_added_accepted_suites": added,
               "round0_scoring_seconds": first_seconds, "round1_scoring_seconds": second_seconds,
               "gap_targets_round0": [r["id"] for r in read_detail(output / "coverage_round0/focal_method_coverage_detail.csv", "KCF_UTG_REPLAY")],
               "gap_targets_round1": [r["id"] for r in read_detail(output / "coverage_round1/focal_method_coverage_detail.csv", "KCF_UTG_REPLAY")]}
    (output / "round_replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
