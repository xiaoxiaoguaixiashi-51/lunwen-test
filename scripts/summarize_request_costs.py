"""Index safe per-target/stage API usage, including blocked and unknown-cost events."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tarfile


def aggregate(events):
    seen = set()
    groups = {}
    legacy = 0
    for event in events:
        identity = event["call_id"]
        if identity in seen:
            raise ValueError("Duplicate call_id: do not count resumed/copied traces twice")
        seen.add(identity)
        target, stage = event.get("target_id"), event.get("stage")
        key = (target, stage)
        group = groups.setdefault(key, {"target_id": target, "stage": stage, "trace_events": 0,
                                       "provider_attempts": 0, "budget_blocked": 0, "unknown_usage_attempts": 0,
                                       "recorded_sdk_retries_not_zero": 0, "usage": Counter(), "status_counts": Counter(),
                                       "provider_elapsed_seconds": 0.0})
        group["trace_events"] += 1
        group["status_counts"][event["status"]] += 1
        attempted = event.get("provider_call_attempted")
        if attempted is None:
            legacy += 1
            attempted = event["status"] in {"ok", "error"}
        if event["status"] == "budget_blocked":
            group["budget_blocked"] += 1
        if not attempted:
            continue
        group["provider_attempts"] += 1
        group["provider_elapsed_seconds"] += event.get("elapsed_seconds", 0)
        if event.get("sdk_max_retries") != 0:
            group["recorded_sdk_retries_not_zero"] += 1
        usage = event.get("usage") or {}
        valid = all(isinstance(usage.get(k), int) and not isinstance(usage[k], bool) and usage[k] >= 0
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
        if valid and usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            valid = False
        if not valid:
            group["unknown_usage_attempts"] += 1
        for name, number in usage.items():
            if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
                group["usage"][name] += number
    rows = list(groups.values())
    totals = Counter()
    usage = Counter()
    for row in rows:
        for field in ("trace_events", "provider_attempts", "budget_blocked", "unknown_usage_attempts", "recorded_sdk_retries_not_zero"):
            totals[field] += row[field]
        usage.update(row["usage"])
    return {"kind": "api_cost_index_not_full_compute_budget", "totals": dict(totals), "known_usage_totals": dict(usage),
            "legacy_events_with_inferred_attempt_flag": legacy, "monetary_cost": None,
            "non_api_costs_measured": False, "full_usage_known": not totals["unknown_usage_attempts"],
            "notes": ["Unknown usage is not zero cost", "SDK retries must be zero for strict attempt accounting",
                      "No retrieval/compiler/JaCoCo runtime cost inferred from API elapsed time"],
            "by_target_stage": sorted(rows, key=lambda r: (str(r["target_id"]), str(r["stage"])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="append", type=Path, default=[])
    parser.add_argument("--archive-trace", action="append", nargs=2, default=[], metavar=("ARCHIVE", "MEMBER"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.trace and not args.archive_trace:
        parser.error("Provide --trace or --archive-trace")
    events, inputs = [], {}
    for path in args.trace:
        content = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(content).hexdigest()
        events.extend(json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip())
    for archive_path, member in args.archive_trace:
        path = Path(archive_path)
        with tarfile.open(path, "r:gz") as archive:
            if len([m for m in archive.getmembers() if m.name == member and m.isfile()]) != 1:
                raise ValueError("Archive trace must be one unique regular member")
            content = archive.extractfile(member).read()
        inputs[str(path) + "::" + member] = {"archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                             "trace_sha256": hashlib.sha256(content).hexdigest()}
        events.extend(json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip())
    result = aggregate(events)
    result["trace_input_sha256"] = inputs
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["totals"]))


if __name__ == "__main__":
    main()
