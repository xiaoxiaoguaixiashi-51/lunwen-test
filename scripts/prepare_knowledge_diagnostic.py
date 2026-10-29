"""Offline-only diagnostic preview. No client, credentials, tokenizer download or API.

Saved source context is historical evidence, not a live source-tree verification.
All previews are non-executable until token budgets and live inputs are verified.
"""
import argparse
import ast
import hashlib
import json
import math
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_kcf_saved_retrieval import audit, rank, read_member
from src.retrieval.dependency_knowledge import compact_record, load_knowledge_records, tokenize

ARCHIVE_SHA = "2037346c9541cdcc764662509473bc86b8a7bb0d2fa2b53fa3a1e78daa159156"
KNOWLEDGE_SHA = "38b5eedac111e59b4d38fcdb2c6e23578b4a3584810a468d94a9db2bc5abace5"
ARMS = ("N", "F", "L", "T")
CONTEXT_SUFFIX = ("\nKeep the test class and every existing @Test method. Do not remove assertions, disable tests, "
                  "add assumptions, or bypass failing paths. Correct an expected value/exception only when justified "
                  "by the supplied implementation. Do not merely copy actual output into expected values.")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tfidf_rank(records, query):
    documents = [tokenize(json.dumps(row, ensure_ascii=False)) for row in records]
    vocabulary = set().union(*documents)
    weights = {term: math.log((1 + len(records)) / (1 + sum(term in doc for doc in documents))) + 1
               for term in sorted(vocabulary)}
    query_terms = tokenize(query) & vocabulary
    qnorm = math.sqrt(sum(weights[t] ** 2 for t in sorted(query_terms)))
    scores = []
    for row, doc in zip(records, documents):
        norm = math.sqrt(sum(weights[t] ** 2 for t in sorted(doc)))
        score = sum(weights[t] ** 2 for t in sorted(query_terms & doc)) / (qnorm * norm) if qnorm and norm else 0
        if score > 0:
            scores.append({"id": row["id"], "score": score})
    return sorted(scores, key=lambda row: (-row["score"], row["id"]))[:3]


def fixed_ids(records):
    return [r["id"] for r in sorted(records, key=lambda r: (digest("kcf-diagnostic-fixed-v1:" + r["id"]), r["id"]))[:3]]


def templates(path):
    # Read literal constants, without importing a module that imports LLMClient.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"SYSTEM_PROMPT", "FIX_PROMPT_TEMPLATE"}:
                    result[target.id] = ast.literal_eval(node.value)
    if len(result) != 2:
        raise ValueError("Missing literal prompt templates")
    return result


def prepare(archive_path, knowledge_path, template_path):
    for path, expected in ((archive_path, ARCHIVE_SHA), (knowledge_path, KNOWLEDGE_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen input hash mismatch: " + path.name)
    replay = audit(archive_path, knowledge_path)
    records = load_knowledge_records(knowledge_path)
    by_id = {r["id"]: r for r in records}
    if len(records) != 12 or len(by_id) != 12 or len(replay["cases"]) != 4:
        raise ValueError("Expected 12 unique records and four failed seeds")
    prompts = templates(template_path)
    units, previews = [], {}
    with tarfile.open(archive_path, "r:gz") as archive:
        if len(archive.getnames()) != len(set(archive.getnames())):
            raise ValueError("Duplicate archive member names")
        index_name = next(n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/seed_input_index.json"))
        prefix = index_name.split("/")[0]
        seeds = {s["method"]["id"]: s for s in json.loads(read_member(archive, index_name))}
        for case in sorted(replay["cases"], key=lambda r: r["id"]):
            identity = case["id"]
            folder = prefix + "/cases/" + identity
            seed = seeds[identity]
            method = seed["method"]
            original = read_member(archive, folder + "/original.java.txt")
            failure = read_member(archive, folder + "/original_failure.log")
            context_text = read_member(archive, folder + "/source_context.json")
            context = json.loads(context_text)["context"]
            if not context.strip():
                raise ValueError("Missing saved source context")
            query = "\n".join([method["fqcn"], method["method"], seed["status"], failure[:6000], original[:6000]])
            if digest(query) != case["query_sha256"]:
                raise ValueError("Query replay mismatch")
            selections = {"N": [], "F": [{"id": i, "score": None} for i in fixed_ids(records)],
                          "L": rank(records, query), "T": tfidf_rank(records, query)}
            common = {"original_sha256": digest(original), "failure_sha256": digest(failure),
                      "saved_context_sha256": digest(context_text), "query_sha256": digest(query)}
            for repeat in range(1, 4):
                order = sorted(ARMS, key=lambda arm: digest(f"kcf-diagnostic-order-v1:{identity}:{repeat}:{arm}"))
                for position, arm in enumerate(order, 1):
                    selected = selections[arm]
                    knowledge = [compact_record(by_id[row["id"]], 0) for row in selected]
                    for record in knowledge:
                        record.pop("retrieval_score", None)
                    slot = json.dumps(knowledge, indent=2, ensure_ascii=False)
                    prompt = prompts["FIX_PROMPT_TEMPLATE"].format(
                        phase=seed["status"], fqcn=method["fqcn"], method_name=method["method"],
                        package_name=method["fqcn"].rsplit(".", 1)[0], test_code=original,
                        failure_output=failure[:10000], retrieved_knowledge=slot)
                    prompt += "\n\n## Verified source context (partial; omissions are unknown, not absence)\n" + context + CONTEXT_SUFFIX
                    messages = [{"role": "system", "content": prompts["SYSTEM_PROMPT"]}, {"role": "user", "content": prompt}]
                    unit_id = f"{identity}__r{repeat}__{arm}"
                    previews[unit_id] = {"preview_only": True, "messages": messages}
                    units.append({"unit_id": unit_id, "case_id": identity, "repeat": repeat, "arm": arm,
                                  "position_in_block": position, **common, "selection": selected,
                                  "prompt_sha256": digest(json.dumps(messages, ensure_ascii=False)),
                                  "knowledge_utf8_bytes": len(slot.encode()), "prompt_utf8_bytes": len(json.dumps(messages, ensure_ascii=False).encode()),
                                  "budget_status": "unmeasured_no_verified_tokenizer", "executable": False})
    if len(units) != 48 or len(previews) != 48:
        raise ValueError("Expected exactly 48 unique units")
    return {"kind": "offline_preview_not_experiment_results", "api_calls": 0, "executable": False,
            "blockers": ["live_source_tree_and_tools_not_reverified", "verified_tokenizer_and_budget_gate_missing",
                         "effective_model_configuration_not_verified", "online_runner_not_implemented"],
            "archive_sha256": ARCHIVE_SHA, "knowledge_sha256": KNOWLEDGE_SHA,
            "template_file_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
            "source_context_origin": "saved_archive_not_live_verification", "units": units}, previews


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template-file", type=Path, default=Path(__file__).with_name("run_stage_b_ours_full_feedback.py"))
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Use a new output directory")
    manifest, previews = prepare(args.archive, args.knowledge, args.template_file)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Raw previews are local-only by default; public manifest contains hashes, not source/log text.
    (args.output_dir / ".gitignore").write_text("previews/\n", encoding="utf-8")
    preview_dir = args.output_dir / "previews"
    preview_dir.mkdir()
    for unit_id, preview in previews.items():
        (preview_dir / (unit_id + ".json")).write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"units": len(manifest["units"]), "api_calls": 0, "executable": False}))


if __name__ == "__main__":
    main()
