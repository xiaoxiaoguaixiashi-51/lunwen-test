"""Offline RQ1/RQ2 preparation: sample-use ledger and explicit cross-stage switches.

No model client or cloud connection. This is not authorization to execute runs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import yaml


def variant_matrix(configs):
    expected = {"Full": (True, True), "A1": (False, True), "A2": (True, True), "A3": (True, False)}
    rows = []
    for variant, (retrieval, guard) in expected.items():
        config = configs[variant]
        if config.get("retrieval", {}).get("enabled") != retrieval or config.get("static_guard", {}).get("enabled") != guard:
            raise ValueError("Unexpected initial-stage switches: " + variant)
        if not config.get("pipeline", {}).get("feedback_enabled"):
            raise ValueError("Ablations must keep feedback enabled")
        feedback_flags, seed_flags = [], []
        if variant in {"A1", "A2"}:
            feedback_flags.append("--disable-coverage-gap-retrieval")
        if variant == "A1":
            feedback_flags.append("--disable-failure-repair-retrieval")
            seed_flags.append("--disable-failure-repair-retrieval")
        if variant == "A3":
            feedback_flags.append("--disable-static-guard")
            seed_flags.append("--disable-static-guard")
        rows.append({"variant": variant, "initial_retrieval": retrieval, "initial_static_guard": guard,
                     "seed_repair_flags_required": seed_flags, "coverage_feedback_flags_required": feedback_flags,
                     "feedback_rounds_enabled": True, "is_effective_run_evidence": False})
    return rows


def audit(root):
    manifest_path = root / "experiments/method_lists/kcf_utg_rq1_methods_v2.json"
    content = manifest_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != "0db76977a9f86c2f7a8d68cfb3dff9511dd331ea42068abbc95df7e2d070359c":
        raise ValueError("Frozen v2 manifest changed")
    methods = json.loads(content)
    pilot_path = root / "experiments/method_lists/kcf_six_project_pilot_20261022.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    ids, development_ids = {m["id"] for m in methods}, {m["id"] for m in pilot}
    if len(methods) != 41 or len(ids) != 41 or len(development_ids) != 6 or not development_ids <= ids:
        raise ValueError("Unexpected method/pilot membership")
    historical_path = root / "experiments/method_lists/kcf_utg_rq1_methods_v1.json"
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    if {m["id"] for m in historical} != ids:
        raise ValueError("Historical and frozen manifest identities differ")
    configs = {}
    for variant, filename in (("Full", "config.kcf_utg.yaml"), ("A1", "config.kcf_utg_a1.yaml"),
                              ("A2", "config.kcf_utg.yaml"), ("A3", "config.kcf_utg_a3.yaml")):
        configs[variant] = yaml.safe_load((root / "config" / filename).read_text(encoding="utf-8"))
    matrix = variant_matrix(configs)
    class_groups = {}
    for method in methods:
        class_groups.setdefault((method["project_id"], method["fqcn"]), []).append(method["id"])
    ledger = [{"id": m["id"], "project_id": m["project_id"], "source_sha256": m["source_sha256"],
               "historical_manifest_member": True, "known_rebuild_development_target": m["id"] in development_ids,
               "remaining_usage_status": "known_development" if m["id"] in development_ids else "not_established_as_unseen",
               "independent_holdout_claim_allowed": False,
               "evidence": "experiments/method_lists/kcf_six_project_pilot_20261022.json" if m["id"] in development_ids
                           else "v1/v2 membership only; no proof of absence of tuning/exposure"}
              for m in sorted(methods, key=lambda m: m["id"])]
    return {"kind": "formal_run_preparation_not_execution", "api_calls": 0, "formal_run_ready": False,
            "method_count": 41, "known_development_methods": 6, "remaining_unseen_status_unresolved": 35,
            "verified_independent_holdout_methods": 0,
            "evosuite_generation_class_count": len(class_groups),
            "evosuite_class_groups": [{"project_id": project, "fqcn": fqcn, "focal_method_ids": sorted(members)}
                                     for (project, fqcn), members in sorted(class_groups.items())],
            "input_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (manifest_path, pilot_path, historical_path)},
            "variants": matrix, "sample_use_ledger": ledger,
            "blocking_gaps": ["formal_compute_budget_and_stop_rules_not_frozen",
                              "hard_cross_stage_budget_enforcement_not_implemented",
                              "per_round_exact_exec_union_not_integrated",
                              "remaining_35_methods_not_verified_unseen",
                              "new_methodological_contribution_not_established",
                              "formal_repetitions_and_new_paid_scope_not_authorized"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo_root.resolve())
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("formal_run_ready", "method_count", "known_development_methods", "api_calls")}))


if __name__ == "__main__":
    main()
