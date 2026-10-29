"""Summarize completed generation and corrected evaluation archives without extraction."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tarfile


def summarize(generation, evaluation):
    hashes = {"generation": "3691060a645f9b317c691fb95ae687e0f3b22af06a137b6b8b3b5a0e069a7fb4",
              "evaluation": "6359602dd99e6674bfcfea5c867c8f7065388211fdf87699c3ba63a52943c10a"}
    for key, path in (("generation", generation), ("evaluation", evaluation)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[key]:
            raise ValueError("Archive hash mismatch")
    patterns = re.compile(rb"sk-[A-Za-z0-9_-]{16,}|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----")
    with tarfile.open(generation, "r:gz") as gen, tarfile.open(evaluation, "r:gz") as ev:
        for archive in (gen, ev):
            if len(archive.getnames()) != len(set(archive.getnames())):
                raise ValueError("Duplicate archive names")
            for member in archive.getmembers():
                if member.isfile() and patterns.search(archive.extractfile(member).read()):
                    raise ValueError("Potential credential pattern; withhold archive")
        gp, ep = "knowledge_diagnostic_20261030/", "knowledge_diagnostic_reeval_20261030/"
        plan = json.load(gen.extractfile(gp + "plan.json"))
        rows = json.load(ev.extractfile(ep + "summary.json"))
        calls = [json.loads(line) for line in gen.extractfile(gp + "llm_calls.jsonl").read().decode().splitlines()]
        expected = {u["unit_id"] for u in plan["units"]}
        if (len(expected) != 48 or len(rows) != 48 or len(calls) != 48 or
                {r["unit_id"] for r in rows} != expected or {r["target_id"] for r in calls} != expected):
            raise ValueError("Incomplete/duplicate calls or evaluation units")
        for event in calls:
            if event["sdk_max_retries"] != 0 or event["request"]["max_tokens"] != 8192:
                raise ValueError("Unexpected request budget")
        usage = Counter()
        for event in calls:
            usage.update({key: value for key, value in event["usage"].items() if isinstance(value, int)})
        for row in rows:
            source = gen.extractfile(gp + row["unit_id"] + "/repaired.java.txt").read()
            if hashlib.sha256(source).hexdigest() != row["generated_source_sha256"]:
                raise ValueError("Evaluated source differs from saved generation")
        return {"kind": "development_diagnostic_not_formal_rq1_rq2", "archive_sha256": hashes,
                "cases": 4, "arms": 4, "repeats": 3, "recorded_api_calls": len(calls),
                "api_status_counts": dict(Counter(e["status"] for e in calls)), "usage": dict(usage),
                "finish_reason_counts": dict(Counter(e["finish_reason"] for e in calls)),
                "summed_api_seconds": sum(e["elapsed_seconds"] for e in calls),
                "max_actual_input_tokens": max(e["usage"]["prompt_tokens"] for e in calls),
                "requests_over_input_limit": sum(e["usage"]["prompt_tokens"] > 12000 for e in calls),
                "monetary_cost": None, "cost_note": "Actual monetary charge not independently verified",
                "evaluation_status_counts": dict(Counter(r["status"] for r in rows)),
                "by_arm": {a: dict(Counter(r["status"] for r in rows if r["arm"] == a)) for a in "NFLT"},
                "by_case": {c: {"status_counts": dict(Counter(r["status"] for r in rows if r["case_id"] == c)),
                                "unique_generated_sources": len({r["generated_source_sha256"] for r in rows if r["case_id"] == c})}
                            for c in sorted({r["case_id"] for r in rows})},
                "passing_suites_pending_semantic_review": sum(r["status"] == "ok" for r in rows),
                "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.generation, args.evaluation)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"api_calls": result["recorded_api_calls"], "by_arm": result["by_arm"]}))


if __name__ == "__main__":
    main()
