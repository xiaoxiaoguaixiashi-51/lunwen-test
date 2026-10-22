"""Summarize and safely archive a single-method API smoke, not formal results."""

import argparse
import csv
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

import yaml


def summarize_calls(events):
    usage = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        reported = [event.get("usage", {}).get(key) for event in events]
        usage[key] = {"known_sum": sum(value for value in reported if value is not None),
                      "unknown_call_count": sum(value is None for value in reported)}
    return {"logical_calls": len(events),
            "successful_calls": sum(event.get("status") == "ok" for event in events),
            "returned_models": sorted({event["response_model"] for event in events if event.get("response_model")}),
            "api_elapsed_seconds_sum": round(sum(event.get("elapsed_seconds", 0) for event in events), 6),
            "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True, help="Private config used only for secret scan")
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--initial-log", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    if args.archive.exists():
        raise FileExistsError("Do not overwrite an evidence archive")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    secret = config["llm"]["api_key"].encode()
    if not secret:
        raise ValueError("Secret scan requires a nonempty configured key")
    shutil.copy2(args.method_list, root / "smoke_method.json")
    shutil.copy2(args.initial_log, root / "initial.log")
    trace = root / "initial/llm_calls.jsonl"
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    with (root / "coverage/ours_jacoco_summary.csv").open(encoding="utf-8", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    record = {"kind": "single_method_api_smoke_not_formal_rq1",
              "requested_model": config["llm"]["model"],
              "initial_generation": json.loads((root / "initial/summary.json").read_text(encoding="utf-8")),
              "cost_observations": summarize_calls(events), "coverage_execution": coverage,
              "focal_coverage": json.loads((root / "evaluation/focal_method_coverage_summary.json").read_text(encoding="utf-8")),
              "money_cost": None, "money_cost_note": "No billing estimate without verified provider pricing and usage semantics"}
    (root / "smoke_summary.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Refusing to export a symlink")
        if path.is_file() and secret in path.read_bytes():
            raise ValueError("Export blocked: configured API key found in evidence")
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz") as archive:
        archive.add(root, arcname=root.name)
    print(json.dumps({"archive": str(args.archive),
                      "sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                      "cost_observations": record["cost_observations"],
                      "focal_coverage": record["focal_coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
