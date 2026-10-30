"""Read-only cross-stage configuration audit. Never creates clients or ledgers."""
import argparse
import hashlib
import json
from pathlib import Path
import yaml

ARMS = ("Full", "A1", "A2", "A3", "RAG")
STAGES = ("initial", "seed_repair", "feedback")
LIMITS = ("max_calls_per_target", "max_total_tokens_per_target", "max_input_tokens_per_call",
          "max_output_tokens_per_call", "framing_reserve", "tokenizer_sha256")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def template(run_root):
    root = Path(run_root)
    if not root.is_absolute():
        raise ValueError("Use an absolute run root on the execution host")
    jobs = []
    for arm in ARMS:
        stages = ("initial",) if arm == "RAG" else STAGES
        for stage in stages:
            flags = []
            if stage != "initial":
                if arm == "A1":
                    flags.append("--disable-failure-repair-retrieval")
                if stage == "feedback" and arm in {"A1", "A2"}:
                    flags.append("--disable-coverage-gap-retrieval")
                if arm == "A3":
                    flags.append("--disable-static-guard")
            jobs.append({"arm": arm, "stage": stage, "config": str(root / "configs" / (arm + ".yaml")),
                         "output_dir": str(root / arm / stage), "ablation_flags": flags})
    return {"kind": "draft_cross_stage_plan_not_execution", "repetition_id": "draft_slot_1",
            "budget_values_frozen": False, "repetitions_frozen": False, "jobs": jobs}


def audit_plan(plan):
    issues, records, ledgers, outputs = [], [], {}, set()
    jobs = plan["jobs"]
    expected = {(arm, stage) for arm in ARMS for stage in (("initial",) if arm == "RAG" else STAGES)}
    identities = [(job["arm"], job["stage"]) for job in jobs]
    if len(set(identities)) != len(identities) or set(identities) != expected:
        raise ValueError("Plan must contain exactly Full/A1/A2/A3 three stages and independent RAG initial")
    reference = None
    kcf_reference = None
    by_arm = {}
    for job in jobs:
        arm, stage = job["arm"], job["stage"]
        label = arm + ":" + stage
        output = Path(job["output_dir"])
        if not output.is_absolute():
            issues.append(label + ":output_not_absolute")
        output = output.resolve()
        if output in outputs or output.exists():
            issues.append(label + ":output_reused_or_exists")
        if any(output in prior.parents or prior in output.parents for prior in outputs):
            issues.append(label + ":nested_output_paths")
        outputs.add(output)
        flags = set(job.get("ablation_flags", []))
        required = set()
        if stage != "initial":
            if arm == "A1":
                required.add("--disable-failure-repair-retrieval")
            if arm == "A3":
                required.add("--disable-static-guard")
            if stage == "feedback" and arm in {"A1", "A2"}:
                required.add("--disable-coverage-gap-retrieval")
        if flags != required:
            issues.append(label + ":ablation_flags_mismatch")
        config_path = Path(job["config"])
        if not config_path.is_file():
            issues.append(label + ":config_missing")
            continue
        try:
            data = config_path.read_bytes()
            config = yaml.safe_load(data)
            if "request_budget" not in config:
                issues.append(label + ":request_budget_missing")
                continue
            llm, budget = config["llm"], config["request_budget"]
            if llm.get("max_retries") != 0 or isinstance(llm.get("max_retries"), bool):
                issues.append(label + ":sdk_retries_not_zero")
            for field in LIMITS[:4]:
                if isinstance(budget[field], bool) or not isinstance(budget[field], int) or budget[field] <= 0:
                    issues.append(label + ":invalid_budget_limit")
            if isinstance(budget["framing_reserve"], bool) or not isinstance(budget["framing_reserve"], int) or budget["framing_reserve"] < 0:
                issues.append(label + ":invalid_framing_reserve")
            tokenizer = Path(budget["tokenizer_json"])
            if not tokenizer.is_absolute() or not tokenizer.is_file() or hashlib.sha256(tokenizer.read_bytes()).hexdigest() != budget["tokenizer_sha256"]:
                issues.append(label + ":tokenizer_missing_or_changed")
            ledger = Path(budget["ledger_path"])
            if not ledger.is_absolute():
                issues.append(label + ":ledger_not_absolute")
            ledger = str(ledger.resolve())
            if Path(ledger).exists():
                issues.append(label + ":ledger_already_exists_fresh_run_required")
            # Compare only explicitly relevant model fields; never output endpoint/key values.
            model = {key: llm.get(key) for key in ("base_url", "model", "temperature", "max_tokens", "thinking", "timeout", "max_retries")}
            if any(model[key] is None for key in ("base_url", "model", "temperature", "max_tokens", "timeout")):
                issues.append(label + ":model_settings_not_explicit")
            common = {"model": model, "budget": {key: budget[key] for key in LIMITS}}
            if reference is None:
                reference = common
            elif common != reference:
                issues.append(label + ":cross_arm_model_or_budget_mismatch")
            if arm != "RAG":
                if config["retrieval"]["enabled"] is not (arm != "A1") or config["static_guard"]["enabled"] is not (arm != "A3"):
                    issues.append(label + ":initial_config_switch_mismatch")
                if config["pipeline"].get("feedback_enabled") is not True:
                    issues.append(label + ":feedback_disabled")
                knowledge = Path(config["retrieval"]["knowledge_path"])
                kcf_common = {"knowledge_sha256": hashlib.sha256(knowledge.read_bytes()).hexdigest(),
                              "max_examples": config["retrieval"].get("max_examples"),
                              "pipeline": config["pipeline"], "java": config.get("java")}
                if kcf_reference is None:
                    kcf_reference = kcf_common
                elif kcf_reference != kcf_common:
                    issues.append(label + ":cross_arm_knowledge_or_pipeline_mismatch")
            signature = {"ledger": ledger, "common": common,
                         "pipeline": config.get("pipeline"), "retrieval": config.get("retrieval"),
                         "static_guard": config.get("static_guard"), "java": config.get("java")}
            if arm in by_arm and by_arm[arm] != signature:
                issues.append(label + ":cross_stage_config_or_ledger_mismatch")
            by_arm[arm] = signature
            if ledger in ledgers and ledgers[ledger] != arm:
                issues.append(label + ":ledger_shared_between_arms")
            ledgers[ledger] = arm
            records.append({"arm": arm, "stage": stage, "config_sha256": hashlib.sha256(data).hexdigest(),
                            "model_budget_fingerprint": fingerprint(common), "ledger_identity_sha256": fingerprint(ledger)})
        except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError):
            issues.append(label + ":invalid_or_incomplete_config")
    return {"kind": "static_plan_preflight_not_run_evidence", "api_calls": 0,
            "configuration_checks_passed": not issues, "formal_run_ready": False,
            "issues": sorted(set(issues)), "checked_stages": records,
            "remaining_checks": ["actual_runner_arguments_and_effective_metadata", "sources_classes_tools_and_reference_hashes",
                                 "formal_budget_stop_rules_and_repetitions_freeze", "evosuite_budget_and_class_mapping",
                                 "sample_use_boundaries_and_methodological_contribution"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", type=Path)
    group.add_argument("--template-run-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = template(args.template_run_root) if args.template_run_root else audit_plan(json.loads(args.plan.read_text()))
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"kind": result["kind"], "api_calls": 0}))


if __name__ == "__main__":
    main()
