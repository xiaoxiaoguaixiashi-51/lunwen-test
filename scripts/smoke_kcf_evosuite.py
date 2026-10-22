"""Validate one EvoSuite generation/execution/JaCoCo chain; no LLM API calls."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--reference-xml-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--java-home", default="/usr/lib/jvm/java-8-openjdk-amd64")
    parser.add_argument("--tools-root", type=Path, default=Path("/root/tools"))
    parser.add_argument("--evaluate-only", action="store_true", help="Retry evaluation using the existing generated tests and XML")
    args = parser.parse_args()
    if args.output_dir.exists() and not args.evaluate_only:
        raise FileExistsError("Smoke output must be a new directory")
    args.output_dir.mkdir(parents=True, exist_ok=args.evaluate_only)
    rows = json.loads(args.method_list.read_text(encoding="utf-8"))
    selected = [r for r in rows if r["fqcn"] == "org.apache.commons.cli.OptionGroup" and r["method"] == "toString"]
    if len(selected) != 1:
        raise ValueError("Expected one OptionGroup smoke target")
    subset = (args.output_dir / "smoke_method.json").resolve()
    if not args.evaluate_only:
        subset.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    elif json.loads(subset.read_text(encoding="utf-8")) != selected:
        raise ValueError("Existing smoke target differs from requested frozen manifest")
    generated = (args.output_dir / "generated").resolve()
    coverage = (args.output_dir / "coverage").resolve()
    evaluated = (args.output_dir / "evaluation").resolve()
    env = {**os.environ, "JAVA_HOME": args.java_home, "PATH": args.java_home + "/bin:" + os.environ["PATH"],
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    commands = [
        [sys.executable, "scripts/maco_stage_b.py", "evosuite-baseline", "--method-list", str(subset),
         "--projects-root", str(args.projects_root), "--evosuite-jar", str(args.tools_root / "evosuite.jar"),
         "--output-dir", str(generated), "--search-budget", "10", "--timeout", "120"],
        [sys.executable, "scripts/run_stage_b_evosuite_coverage.py", "--evosuite-summary",
         str(generated / "evosuite_baseline_summary.csv"), "--evosuite-dir", str(generated),
         "--projects-root", str(args.projects_root), "--evosuite-jar", str(args.tools_root / "evosuite.jar"),
         "--jacoco-agent", str(args.tools_root / "jacocoagent.jar"), "--jacoco-cli", str(args.tools_root / "jacococli.jar"),
         "--output-dir", str(coverage), "--timeout", "120"],
        [sys.executable, "scripts/analyze_focal_method_coverage.py", "--method-list", str(subset),
         "--reference-xml-root", str(args.reference_xml_root), "--approach", f"EvoSuite_smoke={coverage}",
         "--output-dir", str(evaluated)],
    ]
    for index, command in enumerate(commands):
        if args.evaluate_only and index < 2:
            continue
        log_name = "step3_retry.log" if args.evaluate_only else f"step{index + 1}.log"
        with (args.output_dir / log_name).open("x", encoding="utf-8") as log:
            log.write("Command: " + " ".join(command) + "\n")
            log.flush()
            subprocess.run(command, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=240)
    with (coverage / "evosuite_jacoco_summary.csv").open(newline="", encoding="utf-8") as handle:
        statuses = list(csv.DictReader(handle))
    record = {"kind": "toolchain_smoke_only_not_formal_rq1", "method_id": selected[0]["id"],
              "search_budget_seconds": 10, "commands": commands, "coverage_statuses": statuses,
              "evaluation_retry_only": args.evaluate_only,
              "ok": len(statuses) == 1 and statuses[0]["status"] == "ok"}
    (args.output_dir / "smoke_status.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record))
    return 0 if record["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
