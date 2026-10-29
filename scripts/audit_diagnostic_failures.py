"""Enumerate every saved diagnostic failure. Offline, no repair or new generation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tarfile

from scripts.summarize_knowledge_diagnostic import summarize


def audit(generation, evaluation):
    result = summarize(generation, evaluation)  # Checks archive/call/source provenance.
    rows = []
    with tarfile.open(evaluation, "r:gz") as archive:
        for row in result["rows"]:
            prefix = "knowledge_diagnostic_reeval_20261030/" + row["unit_id"] + "/execution/"
            suffix = "/compile.log" if row["status"] == "compile_failed" else "/junit.log"
            names = [n for n in archive.getnames() if n.startswith(prefix) and n.endswith(suffix)]
            if len(names) != 1:
                raise ValueError("Expected one evaluation log for " + row["unit_id"])
            text = archive.extractfile(names[0]).read().decode("utf-8")
            errors = re.findall(r"error: (.+)", text)
            failing_tests = re.findall(r"(?m)^\d+\) (.+)$", text)
            junit = re.search(r"Tests run: (\d+),\s+Failures: (\d+)", text)
            passed = re.search(r"OK \((\d+) tests?\)", text)
            rows.append({"unit_id": row["unit_id"], "case_id": row["case_id"], "arm": row["arm"],
                         "repeat": row["repeat"], "status": row["status"], "log_member": names[0],
                         "compiler_errors": errors, "failing_test_names": failing_tests,
                         "tests_run": int(junit[1]) if junit else int(passed[1]) if passed else None,
                         "junit_failures": int(junit[2]) if junit else 0 if passed else None})
    cases = {}
    for identity in sorted({r["case_id"] for r in rows}):
        group = [r for r in rows if r["case_id"] == identity]
        cases[identity] = {"units": len(group), "status_counts": dict(Counter(r["status"] for r in group)),
                           "failing_tests_occurrences": dict(Counter(t for r in group for t in r["failing_test_names"])),
                           "compiler_error_occurrences": dict(Counter(t for r in group for t in r["compiler_errors"]))}
    return {"kind": "all_saved_failure_logs_not_causal_attribution", "api_calls": 0,
            "archive_sha256": result["archive_sha256"], "cases": cases, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.generation, args.evaluation)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["cases"], indent=2))


if __name__ == "__main__":
    main()
