"""Repair existing failed initial suites before coverage feedback; never rewrite originals."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts.summarize_kcf_pilot import select_status_rows
from src.core.batch_runner import load_method_list
from src.core.llm_client import LLMClient, load_config, trace_target
from src.retrieval.dependency_knowledge import DEFAULT_KNOWLEDGE_PATH, load_knowledge_records
from src.utils.dependency_declarations import grounded_context
from src.utils.experiment_metadata import sha256_file, write_run_metadata
from src.utils.repair_integrity import check_repair_integrity


def prepare_seeds(methods, summary_paths):
    groups = []
    for path in summary_paths:
        with Path(path).open(encoding="utf-8", newline="") as handle:
            groups.append(list(csv.DictReader(handle)))
    rows = select_status_rows(groups)
    if set(rows) != {method["id"] for method in methods}:
        raise ValueError("Execution evidence must account for every frozen target exactly")
    seeds = []
    for method in methods:
        row = rows[method["id"]]
        if row["status"] not in {"ok", "test_failed", "compile_failed"}:
            raise ValueError("Missing/environment/timeout evidence must be resolved before model repair: " + method["id"])
        name = row["test_class"].rsplit(".", 1)[-1]
        path = Path(row["source_dir"]) / (name + ".java")
        if not path.is_file():
            raise FileNotFoundError(path)
        log = Path(row["output_dir"]) / ("junit.log" if row["status"] == "test_failed" else "compile.log")
        if row["status"] != "ok" and not log.is_file():
            raise FileNotFoundError(log)
        if row["status"] == "ok" and (not Path(row["xml_file"]).is_file() or not feedback.report_xml_has_lines(Path(row["xml_file"]))):
            raise ValueError("Passing seed lacks valid coverage XML")
        seeds.append({"method": method, "status": row["status"], "class_name": name,
                      "test_file": str(path), "test_sha256": sha256_file(path),
                      "failure_log": str(log), "xml_file": row.get("xml_file", "")})
    return seeds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", required=True)
    parser.add_argument("--coverage-summary", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--knowledge-path", default=str(DEFAULT_KNOWLEDGE_PATH))
    parser.add_argument("--max-knowledge-examples", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--disable-failure-repair-retrieval", action="store_true")
    parser.add_argument("--disable-static-guard", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and record planned cases with no model requests")
    parser.add_argument("--jacoco-agent", default="/root/tools/jacocoagent.jar")
    parser.add_argument("--jacoco-cli", default="/root/tools/jacococli.jar")
    args = parser.parse_args()
    args.isolate_execution = True
    if args.output_dir.exists():
        raise FileExistsError("Use a fresh output directory; original failed suites remain unchanged")
    methods = load_method_list(args.method_list)
    seeds = prepare_seeds(methods, args.coverage_summary)
    for seed in seeds:
        expected = (args.projects_root / seed["method"]["project_id"]).resolve()
        if not Path(seed["method"]["target"]).resolve().is_relative_to(expected):
            raise ValueError("Target outside frozen project root")
    config = load_config(args.config)
    records = load_knowledge_records(args.knowledge_path)
    root = args.output_dir.resolve()
    root.mkdir(parents=True)
    accepted = root / "accepted_xml"
    review = root / "review_xml"
    accepted.mkdir()
    review.mkdir()
    feedback.write_json(root / "seed_input_index.json", seeds)
    write_run_metadata(root, stage="initial_failure_repair", method_list=args.method_list,
                       config_path=args.config, config=config, knowledge_path=args.knowledge_path,
                       settings={"dry_run": args.dry_run, "max_requests": sum(seed["status"] != "ok" for seed in seeds),
                                 "failure_repair_retrieval_enabled": not args.disable_failure_repair_retrieval,
                                 "static_guard_enabled": not args.disable_static_guard,
                                 "dependency_declaration_context_enabled": not args.disable_static_guard,
                                 "semantic_review_gate": True, "max_tokens": args.max_tokens},
                       inputs={str(path): sha256_file(path) for path in args.coverage_summary})
    os.environ["KCF_LLM_TRACE_PATH"] = str(root / "llm_calls.jsonl")
    os.environ["KCF_PHASE_TRACE_PATH"] = str(root / "phase_calls.jsonl")
    os.environ["KCF_EXPERIMENT_STAGE"] = "initial_failure_repair"
    llm = None if args.dry_run else LLMClient(config)
    statuses, index, review_index = [], [], []
    for seed in seeds:
        method = seed["method"]
        item = root / "cases" / method["id"]
        item.mkdir(parents=True)
        original = Path(seed["test_file"]).read_text(encoding="utf-8")
        (item / "original.java.txt").write_text(original, encoding="utf-8")
        if seed["status"] == "ok":
            target = accepted / (method["id"] + ".xml")
            shutil.copy2(seed["xml_file"], target)
            index.append({"id": method["id"], "status": "ok", "xml_name": target.name,
                          "xml_sha256": sha256_file(target), "semantic_review_required": False,
                          "origin": "unchanged_initial_passing_suite"})
            statuses.append({"id": method["id"], "status": "unchanged_initial_passing_suite"})
            continue
        failure = Path(seed["failure_log"]).read_text(encoding="utf-8", errors="replace")
        (item / "original_failure.log").write_text(failure, encoding="utf-8")
        source_info = grounded_context(method, args.projects_root, not args.disable_static_guard)
        context = source_info["context"]
        feedback.write_json(item / "source_context.json", source_info)
        if args.dry_run:
            statuses.append({"id": method["id"], "status": "planned_failure_repair", "original_status": seed["status"]})
            continue
        try:
            with trace_target(method["id"]):
                repaired, retrieved = feedback.repair_test(llm, original, method, failure, seed["status"],
                                                           records, args, source_context=context)
            (item / "repaired.java.txt").write_text(repaired, encoding="utf-8")
            integrity = check_repair_integrity(original, repaired)
            feedback.write_json(item / "integrity.json", integrity)
            feedback.write_json(item / "retrieval.json", retrieved)
            if not integrity["ok"]:
                result = {"status": "integrity_rejected", "output": str(integrity["errors"])}
            else:
                test = feedback.write_test_file(repaired, item / "generated", seed["class_name"])
                result = feedback.run_generated_test(method, test, seed["class_name"], item / "execution", args, {})
            feedback.write_json(item / "execution_result.json", result)
            status = {"id": method["id"], "status": result["status"], "semantic_review_required": True}
            if result["status"] == "ok":
                target = review / (method["id"] + ".xml")
                shutil.copy2(result["xml_file"], target)
                review_index.append({"id": method["id"], "status": "ok", "xml_name": target.name,
                                     "xml_sha256": sha256_file(target), "semantic_review_required": True,
                                     "repaired_source": str(item / "repaired.java.txt"),
                                     "repaired_source_sha256": sha256_file(item / "repaired.java.txt")})
        except Exception as exc:
            # Trace stores safe request metadata; avoid provider error bodies here.
            status = {"id": method["id"], "status": "error", "error_type": type(exc).__name__}
        statuses.append(status)
        feedback.write_json(item / "status.json", status)
        print(method["project_id"], status["status"], flush=True)
    feedback.write_json(accepted / "accepted_xml_index.json", index)
    feedback.write_json(review / "review_required_index.json", review_index)
    feedback.write_json(root / "failure_repair_summary.json", statuses)
    print(json.dumps(statuses, ensure_ascii=False))


if __name__ == "__main__":
    main()
