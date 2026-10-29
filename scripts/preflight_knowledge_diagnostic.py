"""Live source verification and official tokenizer estimates; never sends requests."""
import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_knowledge_diagnostic import prepare, digest
from scripts.audit_kcf_saved_retrieval import read_member
from src.utils.dependency_declarations import grounded_context


def budget_check(input_estimate, knowledge_estimate):
    # A reserve, not a claim of exact service-side chat framing/tokenization.
    return input_estimate + 256 <= 12000 and knowledge_estimate <= 2048


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--tokenizer-zip", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--tool-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Use a fresh preflight directory")
    if hashlib.sha256(args.method_list.read_bytes()).hexdigest() != "0db76977a9f86c2f7a8d68cfb3dff9511dd331ea42068abbc95df7e2d070359c":
        raise ValueError("Frozen v2 manifest changed")
    manifest, previews = prepare(args.archive, args.knowledge, Path(__file__).with_name("run_stage_b_ours_full_feedback.py"))
    from tokenizers import Tokenizer
    with zipfile.ZipFile(args.tokenizer_zip) as archive:
        raw_tokenizer = archive.read("deepseek_v4_tokenizer/tokenizer.json")
    tokenizer = Tokenizer.from_str(raw_tokenizer.decode("utf-8"))
    count = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
    methods_raw = json.loads(args.method_list.read_text(encoding="utf-8"))
    if isinstance(methods_raw, dict):
        methods_raw = methods_raw["methods"]
    methods = {m["id"]: m for m in methods_raw}
    checks = []
    with tarfile.open(args.archive, "r:gz") as archive:
        index_name = next(n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/seed_input_index.json"))
        prefix = index_name.split("/")[0]
        for identity in sorted({u["case_id"] for u in manifest["units"]}):
            method = methods[identity]
            target = Path(method["target"])
            if not target.resolve().is_relative_to((args.projects_root / method["project_id"]).resolve()):
                raise ValueError("Target outside project root")
            live = grounded_context(method, args.projects_root, True)
            saved = json.loads(read_member(archive, prefix + "/cases/" + identity + "/source_context.json"))
            if live["target_sha256"] != method["source_sha256"]:
                raise ValueError("Live focal source changed")
            # Paths and declaration hashes are part of context: require exact match.
            if live["context"] != saved["context"]:
                raise ValueError("Live context differs from saved preview: " + identity)
            checks.append({"case_id": identity, "source_sha256": live["target_sha256"],
                           "context_sha256": digest(live["context"]), "saved_context_matches_live": True})
    tools = json.loads(args.tool_manifest.read_text(encoding="utf-8"))["tools"]
    for tool in tools:
        path = Path("/root/tools") / tool["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != tool["sha256"]:
            raise ValueError("Tool hash changed: " + tool["file"])
    rows = []
    for unit in manifest["units"]:
        messages = previews[unit["unit_id"]]["messages"]
        prompt = messages[1]["content"]
        # Count the exact serialized knowledge slot from the template section.
        from src.retrieval.dependency_knowledge import compact_record, load_knowledge_records
        records = {r["id"]: r for r in load_knowledge_records(args.knowledge)}
        selected = [compact_record(records[r["id"]], 0) for r in unit["selection"]]
        for item in selected:
            item.pop("retrieval_score", None)
        slot = json.dumps(selected, indent=2, ensure_ascii=False)
        estimated = sum(count(m["content"]) for m in messages)
        knowledge_count = count(slot)
        rows.append({"unit_id": unit["unit_id"], "case_id": unit["case_id"], "arm": unit["arm"],
                     "prompt_sha256": unit["prompt_sha256"], "estimated_content_tokens": estimated,
                     "framing_reserve": 256, "estimated_knowledge_tokens": knowledge_count,
                     "within_estimated_budget": budget_check(estimated, knowledge_count)})
    blocked = sorted({r["case_id"] for r in rows if not r["within_estimated_budget"]})
    result = {"kind": "offline_live_preflight_not_experiment", "api_calls": 0,
              "tokenizer_source": "https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip",
              "tokenizer_zip_sha256": hashlib.sha256(args.tokenizer_zip.read_bytes()).hexdigest(),
              "tokenizer_json_sha256": hashlib.sha256(raw_tokenizer).hexdigest(),
              "token_count_kind": "official_offline_estimate_plus_reserve_not_exact_billed_tokens",
              "live_source_checks": checks, "tools_verified": tools, "budget_rows": rows,
              "blocked_entire_cases": blocked, "all_estimated_budgets_pass": not blocked,
              "online_runner_ready": False}
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "preflight.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"units": len(rows), "api_calls": 0, "blocked_entire_cases": blocked,
                      "max_estimated_content_tokens": max(r["estimated_content_tokens"] for r in rows)}))


if __name__ == "__main__":
    main()
