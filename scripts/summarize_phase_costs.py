"""Validate phase spans; separate nested timings instead of adding them twice."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


def aggregate(events):
    starts, ends = {}, {}
    fields = ("span_id", "parent_span_id", "phase", "target_id", "stage", "session_id", "pid", "started_at")
    for event in events:
        kind = event.get("event")
        if kind not in {"start", "end"}:
            raise ValueError("Unknown span event")
        identity = event["span_id"]
        destination = starts if kind == "start" else ends
        if identity in destination:
            raise ValueError("Duplicate span event: copied traces must not be counted twice")
        if not all(key in event for key in fields):
            raise ValueError("Missing span identity fields")
        destination[identity] = event
    if ends.keys() - starts.keys():
        raise ValueError("End event has no start")
    groups = defaultdict(lambda: {"started": 0, "completed": 0, "incomplete": 0,
                                  "exceptions": 0, "inclusive_seconds": 0.0, "root_seconds": 0.0})
    for identity, start in starts.items():
        parent = start["parent_span_id"]
        if parent is not None:
            if parent not in starts or parent == identity:
                raise ValueError("Missing or self parent span")
            cursor, seen = parent, {identity}
            while cursor is not None:
                if cursor in seen or cursor not in starts:
                    raise ValueError("Invalid parent chain")
                seen.add(cursor)
                cursor = starts[cursor]["parent_span_id"]
            if starts[parent]["session_id"] != start["session_id"]:
                raise ValueError("Cross-session parent span")
        group = groups[(start["target_id"], start["stage"], start["phase"])]
        group["started"] += 1
        end = ends.get(identity)
        if end is None:
            group["incomplete"] += 1
            continue
        if any(start[key] != end[key] for key in fields):
            raise ValueError("Span identity changed")
        seconds = end["elapsed_seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid elapsed seconds")
        if end.get("status") not in {"returned", "exception"}:
            raise ValueError("Unknown span status")
        group["completed"] += 1
        group["exceptions"] += end["status"] == "exception"
        group["inclusive_seconds"] += seconds
        if parent is None:
            group["root_seconds"] += seconds
    rows = [{"target_id": key[0], "stage": key[1], "phase": key[2], **value}
            for key, value in sorted(groups.items(), key=lambda pair: str(pair[0]))]
    return {"kind": "phase_wall_time_index_not_full_compute_budget", "full_compute_cost_known": False,
            "incomplete_spans": len(starts.keys() - ends.keys()),
            "sum_completed_root_seconds": sum(row["root_seconds"] for row in rows),
            "by_target_stage_phase": rows,
            "notes": ["Inclusive spans overlap: never sum all phases or add API/Java timers to parent spans",
                      "Root seconds are accumulated operation time, not concurrent makespan or CPU/GPU time",
                      "returned means Python returned, not compile/test success",
                      "Incomplete spans have unknown cost, not zero; uninstrumented work remains unknown"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    events, inputs = [], {}
    for path in args.trace:
        data = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(data).hexdigest()
        events.extend(json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip())
    result = aggregate(events)
    result["trace_input_sha256"] = inputs
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("incomplete_spans", "sum_completed_root_seconds")}))


if __name__ == "__main__":
    main()
