"""Verify pinned source targets and optionally build each KCF project."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_focal_method_coverage import find_method_ranges


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inspect_targets(methods: list[dict], projects_root: Path) -> list[dict]:
    rows = []
    for item in methods:
        source = projects_root / item["project_id"] / item["target_relative"]
        row = {"id": item["id"], "project_id": item["project_id"], "method": item["method"],
               "source": str(source), "exists": source.is_file()}
        if source.is_file():
            row["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            ranges = find_method_ranges(source.read_text(encoding="utf-8"), item["method"])
            row["ranges"] = [{"start": r.start, "end": r.end} for r in ranges]
            row["match_count"] = len(ranges)
        rows.append(row)
    return rows


def build(project: dict, projects_root: Path, output: Path, timeout: int,
          maven_settings: Path | None = None, java_override: str | None = None) -> dict:
    started = time.monotonic()
    java_home = java_override or f"/usr/lib/jvm/java-{project['java']}-openjdk-amd64"
    env = {**os.environ, "JAVA_HOME": java_home, "PATH": java_home + "/bin:" + os.environ["PATH"],
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    row = {"project_id": project["project_id"], "java_home": java_home, "commands": [], "status": "ok"}
    for index, configured_command in enumerate(project["build_commands"]):
        command = [part for part in configured_command if part != "-q"]
        if command[0] == "mvn":
            command.insert(1, "-B")
            if maven_settings:
                command[1:1] = ["-s", str(maven_settings.resolve())]
        log_file = output / f"{project['project_id']}.build.{index + 1}.log"
        with log_file.open("w", encoding="utf-8") as log:
            log.write("Command: " + " ".join(command) + "\nJAVA_HOME=" + java_home + "\n")
            log.flush()
            process = subprocess.Popen(command, cwd=projects_root / project["project_id"],
                                       stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
                status = "ok" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                code, status = -1, "timeout"
        row["commands"].append({"argv": command, "return_code": code, "status": status, "log": str(log_file)})
        if status != "ok":
            row["status"] = status
            break
    row["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--project-manifest", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--project-id", action="append", help="Build only the specified project(s)")
    parser.add_argument("--maven-settings", type=Path)
    parser.add_argument("--java-home", help="Explicit JDK override, recorded in build evidence")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    methods = json.loads(args.method_list.read_text(encoding="utf-8"))
    projects = json.loads(args.project_manifest.read_text(encoding="utf-8"))
    if args.project_id:
        unknown = set(args.project_id) - {p["project_id"] for p in projects}
        if unknown:
            parser.error(f"Unknown projects: {sorted(unknown)}")
        projects = [p for p in projects if p["project_id"] in args.project_id]
    targets = inspect_targets(methods, args.projects_root)
    report = {"method_count": len(targets), "unique_ids": len({r["id"] for r in targets}),
              "targets_missing": sum(not r["exists"] for r in targets),
              "methods_unmatched": sum(not r.get("match_count") for r in targets),
              "ambiguous_methods": sum(r.get("match_count", 0) > 1 for r in targets), "methods": targets}
    write_json(args.output_dir / "target_verification.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "methods"}), flush=True)
    if report["targets_missing"] or report["methods_unmatched"] or len(targets) != 41 or report["unique_ids"] != 41:
        return 2
    rows = []
    if args.build:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            pending = {pool.submit(build, p, args.projects_root, args.output_dir, args.timeout,
                                   args.maven_settings, args.java_home): p for p in projects}
            for future in concurrent.futures.as_completed(pending):
                try:
                    row = future.result()
                except Exception as exc:
                    row = {"project_id": pending[future]["project_id"], "status": "error", "error": str(exc)}
                rows.append(row)
                print(json.dumps(row), flush=True)
                write_json(args.output_dir / "build_summary.json", sorted(rows, key=lambda r: r["project_id"]))
    return 0 if all(r["status"] == "ok" for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
