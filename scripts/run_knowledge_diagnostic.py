"""Execute the bounded four-case diagnostic only after live preflight. No retries/resume."""
import argparse
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_knowledge_diagnostic import prepare, digest
from scripts.probe_kcf_api_once import safe_settings
from scripts.audit_kcf_saved_retrieval import read_member
from src.core.llm_client import LLMClient, load_config, trace_target
from src.utils.dependency_declarations import grounded_context
from src.utils.repair_integrity import check_repair_integrity
from scripts import run_stage_b_ours_full_feedback as feedback


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_plan(manifest, preflight):
    units = manifest["units"]
    if len(units) != 48 or len({u["unit_id"] for u in units}) != 48:
        raise ValueError("Exactly 48 unique planned units required")
    rows = preflight["budget_rows"]
    if len(rows) != 48 or len({u["unit_id"] for u in rows}) != 48:
        raise ValueError("Incomplete budget preflight")
    verified = {r["unit_id"]: r for r in rows}
    if preflight["blocked_entire_cases"] or not preflight["all_estimated_budgets_pass"]:
        raise ValueError("Budget preflight blocked")
    for unit in units:
        row = verified[unit["unit_id"]]
        if row["prompt_sha256"] != unit["prompt_sha256"] or not row["within_estimated_budget"]:
            raise ValueError("Prompt changed after budget preflight")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    manifest, previews = prepare(args.archive, args.knowledge, Path(__file__).with_name("run_stage_b_ours_full_feedback.py"))
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    validate_plan(manifest, preflight)
    if hashlib.sha256(args.method_list.read_bytes()).hexdigest() != "0db76977a9f86c2f7a8d68cfb3dff9511dd331ea42068abbc95df7e2d070359c":
        raise ValueError("Method manifest changed")
    methods_raw = json.loads(args.method_list.read_text(encoding="utf-8"))
    if isinstance(methods_raw, dict):
        methods_raw = methods_raw["methods"]
    methods = {m["id"]: m for m in methods_raw}
    for check in preflight["live_source_checks"]:
        live = grounded_context(methods[check["case_id"]], args.projects_root, True)
        if live["target_sha256"] != check["source_sha256"] or digest(live["context"]) != check["context_sha256"]:
            raise ValueError("Live context changed after preflight")
    if not args.config.is_file():
        raise FileNotFoundError("Exact private config required")
    config = load_config(str(args.config))
    settings = safe_settings(config)
    if settings["temperature"] != 0.2:
        raise ValueError("Unexpected temperature")
    if not args.execute:
        print(json.dumps({"planned_calls": 48, "api_calls": 0, "preflight_matches": True}))
        return
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write(args.output_dir / "plan.json", manifest)
    write(args.output_dir / "preflight.json", preflight)
    write(args.output_dir / "settings.json", {"model": settings["model"], "thinking": settings["thinking"],
          "temperature": 0.2, "max_tokens": 8192, "max_retries": 0, "request_timeout": 120,
          "code_sha256": {str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (Path(__file__).resolve(), Path(__file__).with_name("prepare_knowledge_diagnostic.py"),
                                    Path(feedback.__file__), Path(__file__).resolve().parents[1] / "src/core/llm_client.py")},
          "semantic_review_required": True, "budget_kind": "official_offline_estimate_plus_256_reserve"})
    config["llm"].update(max_retries=0, timeout=120, max_tokens=8192)
    os.environ["KCF_LLM_TRACE_PATH"] = str(args.output_dir / "llm_calls.jsonl")
    os.environ["KCF_EXPERIMENT_STAGE"] = "knowledge_selection_development_diagnostic"
    llm = LLMClient(config)
    run_args = SimpleNamespace(projects_root=args.projects_root, timeout=60,
                               jacoco_agent="/root/tools/jacocoagent.jar", jacoco_cli="/root/tools/jacococli.jar",
                               isolate_execution=True, disable_static_guard=False)
    seeds, originals = {}, {}
    with tarfile.open(args.archive, "r:gz") as archive:
        name = next(n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/seed_input_index.json"))
        seeds = {s["method"]["id"]: s for s in json.loads(read_member(archive, name))}
        for identity in {u["case_id"] for u in manifest["units"]}:
            originals[identity] = read_member(archive, name.split("/")[0] + "/cases/" + identity + "/original.java.txt")
    statuses = []
    for number, unit in enumerate(manifest["units"], 1):
        item = args.output_dir / unit["unit_id"]
        item.mkdir()
        row = {"unit_id": unit["unit_id"], "case_id": unit["case_id"], "arm": unit["arm"],
               "repeat": unit["repeat"], "status": "request_started", "semantic_review_required": True}
        write(item / "status.json", row)
        try:
            with trace_target(unit["unit_id"]):
                response = llm.chat(previews[unit["unit_id"]]["messages"], max_tokens=8192)
            (item / "raw_response.txt").write_text(response, encoding="utf-8")
            method = methods[unit["case_id"]]
            code = feedback.format_generated_code(feedback.safe_text(feedback.extract_fenced_block(response, "java")),
                                                   feedback.package_from_item(method), run_args)
            (item / "repaired.java.txt").write_text(code, encoding="utf-8")
            integrity = check_repair_integrity(originals[unit["case_id"]], code)
            write(item / "integrity.json", integrity)
            if not integrity["ok"]:
                row["status"] = "integrity_rejected"
            else:
                seed = seeds[unit["case_id"]]
                test = feedback.write_test_file(code, item / "generated", seed["class_name"])
                result = feedback.run_generated_test(method, test, seed["class_name"], item / "execution", run_args, {})
                write(item / "execution_result.json", result)
                row["status"] = result["status"]
        except Exception as exc:
            row.update(status="error", error_type=type(exc).__name__, status_code=getattr(exc, "status_code", None))
        write(item / "status.json", row)
        statuses.append(row)
        write(args.output_dir / "summary.json", statuses)
        print(json.dumps({"completed": number, **row}), flush=True)


if __name__ == "__main__":
    main()
