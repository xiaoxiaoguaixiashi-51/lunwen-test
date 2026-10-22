"""Read-only diagnostic of saved seed-repair retrieval; no generation or filtering.

Replay must match saved IDs AND scores before reporting component-only rankings.
Removing query components is an offline ranking diagnostic, not a new treatment
or evidence that knowledge caused a failure. No source/test/key is exported.
"""

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.retrieval.dependency_knowledge import load_knowledge_records, score_record, tokenize


def rank(records, query, k=3):
    tokens = tokenize(query)
    scored = [(score_record(record, tokens, "", {}), str(record["id"])) for record in records]
    return [{"id": identity, "score": score} for score, identity in sorted(scored, key=lambda x: (-x[0], x[1])) if score > 0][:k]


def read_member(archive, name):
    member = archive.getmember(name)
    if not member.isfile():
        raise ValueError("Expected regular archived evidence")
    with archive.extractfile(member) as handle:
        return handle.read().decode("utf-8")


def audit(archive_path, knowledge_path):
    records = load_knowledge_records(knowledge_path)
    rows = []
    with tarfile.open(archive_path, "r:gz") as archive:
        indexes = [name for name in archive.getnames() if name.count("/") == 1 and name.endswith("/seed_input_index.json")]
        if len(indexes) != 1:
            raise ValueError("Expected exactly one saved seed input index")
        prefix = indexes[0].split("/")[0]
        seeds = json.loads(read_member(archive, indexes[0]))
        for seed in seeds:
            if seed["status"] not in {"compile_failed", "test_failed"}:
                continue
            method = seed["method"]
            folder = f"{prefix}/cases/{method['id']}"
            source = read_member(archive, folder + "/original.java.txt")
            failure = read_member(archive, folder + "/original_failure.log")
            saved = json.loads(read_member(archive, folder + "/retrieval.json"))
            if len(saved) != 3:
                raise ValueError("This diagnostic is scoped to the saved Top-3 protocol")
            parts = {"target": method["fqcn"] + "\n" + method["method"], "phase": seed["status"],
                     "failure": failure[:6000], "test": source[:6000]}
            query = "\n".join(parts.values())
            replay = rank(records, query)
            expected = [{"id": item["id"], "score": item["retrieval_score"]} for item in saved]
            if replay != expected:
                raise ValueError("Saved ranking replay mismatch for " + method["id"])
            status = json.loads(read_member(archive, folder + "/status.json"))
            rows.append({"id": method["id"], "project_id": method["project_id"],
                         "original_status": seed["status"], "repair_status": status["status"],
                         "replay_exact_match": True, "saved_top3": replay,
                         "component_only_top3": {name: rank(records, text) for name, text in parts.items()},
                         "component_token_counts": {name: len(tokenize(text)) for name, text in parts.items()},
                         "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                         "selected_record_token_overlap": {
                             item["id"]: sorted(tokenize(query) & tokenize(json.dumps(next(
                                 record for record in records if record["id"] == item["id"]), ensure_ascii=False)))
                             for item in replay}})
    return {"kind": "offline_saved_retrieval_replay_not_causal_or_effectiveness_experiment",
            "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "knowledge_sha256": hashlib.sha256(knowledge_path.read_bytes()).hexdigest(),
            "records_total": len(records), "failed_seed_cases_total": len(rows), "api_calls": 0,
            "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--knowledge", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.archive, args.knowledge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"cases": len(result["cases"]), "all_replays_match": True, "api_calls": 0}))


if __name__ == "__main__":
    main()
