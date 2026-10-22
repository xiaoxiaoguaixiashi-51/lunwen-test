"""Join interrupted/continued pilot evidence without treating failing tests as valid coverage."""

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_focal_method_coverage import load_focal_methods, load_coverage_xmls, write_outputs
from scripts.summarize_kcf_api_smoke import summarize_calls


def select_status_rows(groups):
    selected = {}
    for rows in groups:
        for row in rows:
            if row["id"] not in selected or row["status"] != "missing_status":
                selected[row["id"]] = row
    return selected


def junit_counts(text):
    ok = re.search(r"OK \((\d+) tests?\)", text)
    failed = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", text)
    if ok:
        return {"tests_run": int(ok[1]), "failures": 0}
    if failed:
        return {"tests_run": int(failed[1]), "failures": int(failed[2])}
    return {"tests_run": None, "failures": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--reference-xml-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-config-for-scan", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.archive.exists():
        raise FileExistsError("Do not overwrite pilot summaries")
    groups, events, provenance = [], [], []
    for root in args.run_dir:
        with (root / "coverage/ours_jacoco_summary.csv").open(encoding="utf-8", newline="") as handle:
            groups.append(list(csv.DictReader(handle)))
        calls = [json.loads(line) for line in (root / "initial/llm_calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        events.extend(calls)
        meta = json.loads((root / "initial/run_metadata.json").read_text(encoding="utf-8"))
        provenance.append({"run_dir": str(root), "repository_revision": meta["repository_revision"],
                           "method_list_sha256": meta["method_list_sha256"], "calls": summarize_calls(calls)})
    chosen = select_status_rows(groups)
    methods = json.loads(args.method_list.read_text(encoding="utf-8"))
    if set(chosen) != {method["id"] for method in methods}:
        raise ValueError("Pilot status IDs differ from frozen target IDs")
    args.output_dir.mkdir(parents=True)
    rows = []
    passing = args.output_dir / "passing_xml"
    diagnostic = args.output_dir / "diagnostic_xml"
    passing.mkdir()
    diagnostic.mkdir()
    for method in methods:
        row = chosen[method["id"]]
        junit = Path(row["output_dir"]) / "junit.log"
        rows.append({"id": row["id"], "project_id": method["project_id"], "method": method["method"],
                     "status": row["status"], "evaluated_compile_success": row.get("compile_code") == "0",
                     "pipeline_generation_success": row.get("generation_success"),
                     "junit": junit_counts(junit.read_text(encoding="utf-8")) if junit.exists() else junit_counts(""),
                     "calls_including_interrupted_attempts": summarize_calls([event for event in events if event.get("target_id") == row["id"]])})
        if row.get("xml_file"):
            source = Path(row["xml_file"])
            shutil.copy2(source, diagnostic / (row["id"] + ".xml"))
            if row["status"] == "ok":
                shutil.copy2(source, passing / (row["id"] + ".xml"))
    focal = load_focal_methods(args.method_list, None, [])
    reference = load_coverage_xmls(args.reference_xml_root)
    write_outputs(focal, [("Passing_suites_only", load_coverage_xmls(passing))], args.output_dir / "passing_evaluation", reference)
    write_outputs(focal, [("Diagnostic_including_failing_suites", load_coverage_xmls(diagnostic))], args.output_dir / "diagnostic_evaluation", reference)
    summary = {"kind": "six_project_initial_workflow_pilot_not_formal_rq1_or_rq2", "methods_total": len(methods),
               "method_list_sha256": hashlib.sha256(args.method_list.read_bytes()).hexdigest(),
               "evaluated_compile_successes": sum(row["evaluated_compile_success"] for row in rows),
               "passing_suites": sum(row["status"] == "ok" for row in rows), "per_method": rows,
               "all_costs_including_interrupted_attempt": summarize_calls(events), "source_runs": provenance,
               "coverage_policy": "Passing suites only is conservative valid-suite coverage. All XML including failing suites is diagnostic only. Fixed denominator retains all six targets."}
    (args.output_dir / "pilot_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    secret = yaml.safe_load(args.private_config_for_scan.read_text(encoding="utf-8"))["llm"]["api_key"].encode()
    if not secret:
        raise ValueError("Empty key cannot be used for export scan")
    for path in args.output_dir.rglob("*"):
        if path.is_symlink() or (path.is_file() and secret in path.read_bytes()):
            raise ValueError("Unsafe evidence export blocked")
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz") as archive:
        archive.add(args.output_dir, arcname=args.output_dir.name)
    print("Archive SHA-256:", hashlib.sha256(args.archive.read_bytes()).hexdigest())
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
