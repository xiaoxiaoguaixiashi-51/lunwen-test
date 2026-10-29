"""Evaluate saved diagnostic generations with absolute paths. Never calls an API."""
import argparse
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts.audit_kcf_saved_retrieval import read_member
from scripts.prepare_knowledge_diagnostic import digest, ARCHIVE_SHA
from src.utils.repair_integrity import check_repair_integrity
import hashlib
import time


def absolute_output(path):
    return Path(path).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=0, help="Wait for generation completion, with no API calls")
    args = parser.parse_args()
    args.output_dir = absolute_output(args.output_dir)
    if args.output_dir.exists():
        raise FileExistsError("Original evaluations remain unchanged; use fresh output")
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Original seed archive changed")
    if hashlib.sha256(args.method_list.read_bytes()).hexdigest() != "0db76977a9f86c2f7a8d68cfb3dff9511dd331ea42068abbc95df7e2d070359c":
        raise ValueError("Frozen method list changed")
    plan = json.loads((args.run_root / "plan.json").read_text(encoding="utf-8"))
    deadline = time.monotonic() + args.wait_seconds
    while True:
        try:
            prior = json.loads((args.run_root / "summary.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            prior = []
        if len(prior) == 48 or time.monotonic() >= deadline:
            break
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    if len(prior) != 48 or {r["unit_id"] for r in prior} != {r["unit_id"] for r in plan["units"]}:
        raise ValueError("Wait for all 48 units; incomplete generation run")
    prior = {r["unit_id"]: r for r in prior}
    raw = json.loads(args.method_list.read_text(encoding="utf-8"))
    methods = {m["id"]: m for m in (raw["methods"] if isinstance(raw, dict) else raw)}
    originals = {}
    with tarfile.open(args.archive, "r:gz") as archive:
        name = next(n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/seed_input_index.json"))
        seeds = {s["method"]["id"]: s for s in json.loads(read_member(archive, name))}
        for identity in {u["case_id"] for u in plan["units"]}:
            originals[identity] = read_member(archive, name.split("/")[0] + "/cases/" + identity + "/original.java.txt")
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "provenance.json").write_text(json.dumps({
        "api_calls": 0, "reason": "correct_relative_path_evaluation_harness_error",
        "run_plan_sha256": hashlib.sha256((args.run_root / "plan.json").read_bytes()).hexdigest(),
        "original_summary_sha256": hashlib.sha256((args.run_root / "summary.json").read_bytes()).hexdigest(),
        "semantic_review_required": True}, indent=2) + "\n", encoding="utf-8")
    run_args = SimpleNamespace(projects_root=args.projects_root.resolve(), timeout=60,
                               jacoco_agent="/root/tools/jacocoagent.jar", jacoco_cli="/root/tools/jacococli.jar",
                               isolate_execution=True, disable_static_guard=False)
    rows = []
    for unit in plan["units"]:
        row = {"unit_id": unit["unit_id"], "case_id": unit["case_id"], "arm": unit["arm"],
               "repeat": unit["repeat"], "original_status": prior[unit["unit_id"]]["status"],
               "semantic_review_required": True}
        saved = args.run_root / unit["unit_id"] / "repaired.java.txt"
        item = args.output_dir / unit["unit_id"]
        item.mkdir()
        if not saved.is_file():
            row["status"] = "missing_generated_source"
        else:
            code = saved.read_text(encoding="utf-8")
            if digest(originals[unit["case_id"]]) != unit["original_sha256"]:
                raise ValueError("Original seed mismatch")
            row["generated_source_sha256"] = hashlib.sha256(saved.read_bytes()).hexdigest()
            integrity = check_repair_integrity(originals[unit["case_id"]], code)
            (item / "integrity.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
            if not integrity["ok"]:
                row["status"] = "integrity_rejected"
            else:
                method = methods[unit["case_id"]]
                seed = seeds[unit["case_id"]]
                test = feedback.write_test_file(code, item / "generated", seed["class_name"])
                result = feedback.run_generated_test(method, test, seed["class_name"], item / "execution", run_args, {})
                (item / "execution_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                row["status"] = result["status"]
        rows.append(row)
        (args.output_dir / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"completed": len(rows), **row}), flush=True)


if __name__ == "__main__":
    main()
