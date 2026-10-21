"""Prepare and run the MACO-aligned 41 Stage B infrastructure.

This script intentionally handles only non-LLM Stage B work:

* project checkout/environment setup
* buildability checks
* MACO-aligned focal-method candidate scoring and selection
* EvoSuite baseline generation commands

It does not claim strict MACO reproduction. The selected method list is an
aligned fallback until the original MACO 41 focal-method list is available.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.collect_java_methods import collect_methods
from scripts.run_defects4j_generated_tests import format_rate
from scripts.analyze_focal_method_coverage import (
    find_method_ranges,
    load_coverage_xmls,
    load_focal_methods,
    parse_approach,
    parse_prefix_map,
    write_outputs,
)
from src.metrics.dcci import score_method


DEFAULT_MANIFEST = Path("experiments/maco_aligned_41_projects.json")
MDCI_THRESHOLD = 1.0


@dataclass(frozen=True)
class ProjectSpec:
    project_id: str
    name: str
    version: str
    java: int
    target_methods: int
    repo_url: str
    refs: list[str]
    source_roots: list[str]
    build_commands: list[list[str]]
    notes: str = ""


def load_projects(path: Path) -> list[ProjectSpec]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Project manifest must be a JSON array")
    projects = []
    for index, row in enumerate(rows):
        required = {"project_id", "name", "version", "java", "target_methods", "source_roots", "build_commands"}
        missing = required - set(row)
        if missing:
            raise ValueError(f"Project #{index} is missing fields: {sorted(missing)}")
        projects.append(
            ProjectSpec(
                project_id=str(row["project_id"]),
                name=str(row["name"]),
                version=str(row["version"]),
                java=int(row["java"]),
                target_methods=int(row["target_methods"]),
                repo_url=str(row.get("repo_url", "")),
                refs=[str(value) for value in row.get("refs", [])],
                source_roots=[str(value) for value in row.get("source_roots", [])],
                build_commands=[[str(part) for part in command] for command in row.get("build_commands", [])],
                notes=str(row.get("notes", "")),
            )
        )
    return projects


def project_dir(projects_root: Path, project: ProjectSpec) -> Path:
    return projects_root / project.project_id


def run_command(command: list[str], cwd: Path, timeout: int) -> tuple[str, int, str]:
    def coerce_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    try:
        proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        return "ok" if proc.returncode == 0 else "failed", proc.returncode, output
    except FileNotFoundError as exc:
        return "tool_missing", 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        output = coerce_output(exc.stdout) + coerce_output(exc.stderr) + "\nTIMEOUT\n"
        return "timeout", -1, output


def checkout_projects(projects: list[ProjectSpec], projects_root: Path, output_dir: Path, timeout: int) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for project in projects:
        dest = project_dir(projects_root, project)
        log_file = output_dir / f"{project.project_id}.checkout.log"
        if not project.repo_url:
            row = checkout_row(project, dest, "missing_repo_url", "", log_file)
            write_log(log_file, project.notes or "Repository URL is not fixed yet.\n")
            rows.append(row)
            continue
        if not dest.exists():
            status, return_code, output = run_command(["git", "clone", project.repo_url, str(dest)], projects_root, timeout)
            write_log(log_file, output)
            if status != "ok":
                rows.append(checkout_row(project, dest, status, "", log_file, return_code))
                continue
        checkout_status, checkout_ref, checkout_output, checkout_code = checkout_first_ref(dest, project.refs, timeout)
        append_log(log_file, checkout_output)
        rows.append(checkout_row(project, dest, checkout_status, checkout_ref, log_file, checkout_code))
    return rows


def checkout_first_ref(dest: Path, refs: list[str], timeout: int) -> tuple[str, str, str, int]:
    if not refs:
        return "ok", "", "No refs supplied; keeping default branch.\n", 0
    messages = []
    for ref in refs:
        status, return_code, output = run_command(["git", "checkout", ref], dest, timeout)
        messages.append(f"$ git checkout {ref}\n{output}\n")
        if status == "ok":
            return "ok", ref, "".join(messages), return_code
    return "failed", "", "".join(messages), return_code


def checkout_row(
    project: ProjectSpec,
    dest: Path,
    status: str,
    checkout_ref: str,
    log_file: Path,
    return_code: int | str = "",
) -> dict:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "version": project.version,
        "status": status,
        "checkout_ref": checkout_ref,
        "project_dir": str(dest),
        "return_code": return_code,
        "log_file": str(log_file),
    }


def buildability_check(projects: list[ProjectSpec], projects_root: Path, output_dir: Path, timeout: int) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for project in projects:
        dest = project_dir(projects_root, project)
        if not dest.exists():
            rows.append(build_row(project, "missing_checkout", "", "", output_dir / f"{project.project_id}.build.log"))
            continue
        for index, command in enumerate(project.build_commands):
            log_file = output_dir / f"{project.project_id}.build.{index + 1}.log"
            status, return_code, output = run_command(command, dest, timeout)
            write_log(log_file, output)
            rows.append(build_row(project, status, command, return_code, log_file, dest))
    return rows


def build_row(
    project: ProjectSpec,
    status: str,
    command: list[str] | str,
    return_code: int | str,
    log_file: Path,
    project_root: Path | None = None,
) -> dict:
    classpath_entries = discover_classpath_entries(project_root) if project_root else []
    return {
        "project_id": project.project_id,
        "name": project.name,
        "version": project.version,
        "java": project.java,
        "status": status,
        "command": " ".join(command) if isinstance(command, list) else command,
        "return_code": return_code,
        "log_file": str(log_file),
        "classpath_entries": os.pathsep.join(str(path) for path in classpath_entries),
        "classpath_entry_count": len(classpath_entries),
    }


def discover_classpath_entries(project_root: Path | None) -> list[Path]:
    if not project_root:
        return []
    candidates = [
        project_root / "target" / "classes",
        project_root / "target" / "test-classes",
        project_root / "build" / "classes" / "java" / "main",
        project_root / "build" / "classes" / "java" / "test",
        project_root / "build" / "classes" / "main",
        project_root / "build" / "classes" / "test",
        project_root / "build" / "classes",
        project_root / "build" / "test-classes",
        project_root / "build" / "core",
        project_root / "core" / "target" / "classes",
        project_root / "core" / "target" / "test-classes",
    ]
    return [path for path in candidates if path.exists()]


def collect_candidates(projects: list[ProjectSpec], projects_root: Path, skip_errors: bool = True) -> list[dict]:
    candidates: list[dict] = []
    for project in projects:
        root = project_dir(projects_root, project)
        if not root.exists():
            continue
        for source_root_value in project.source_roots:
            source_root = root / source_root_value
            if not source_root.exists():
                continue
            for row in collect_methods(source_root, project.project_id, "maco-aligned-41"):
                scored = score_candidate(row, project, root, source_root, skip_errors=skip_errors)
                if scored:
                    candidates.append(scored)
    candidates.sort(key=lambda item: (item["project_id"], -float(item["mdci"]), -float(item["dcci"]), item["id"]))
    return candidates


def score_candidate(
    row: dict,
    project: ProjectSpec,
    root: Path,
    source_root: Path,
    skip_errors: bool,
) -> dict | None:
    target = str(Path(row["target"]))
    try:
        dcci_result = score_method(target, row.get("method"))
        dcci = float(dcci_result.get("dcci", 0.0))
    except Exception as exc:
        if not skip_errors:
            raise
        dcci = 0.0
        row["dcci_error"] = f"{type(exc).__name__}: {exc}"

    mdci, mdci_breakdown = score_mdci_heuristic(Path(target), str(row["method"]))
    rel_target = str(Path(target).relative_to(root))
    source_rel = str(source_root.relative_to(root))
    return {
        **row,
        "id": f"{project.project_id}-{row['id']}",
        "project_id": project.project_id,
        "project_name": project.name,
        "project_version": project.version,
        "java": project.java,
        "target": target,
        "target_relative": rel_target,
        "source_root": str(source_root),
        "source_root_relative": source_rel,
        "dcci": round(dcci, 4),
        "mdci": mdci,
        "mdci_breakdown": mdci_breakdown,
    }


def score_mdci_heuristic(java_file: Path, method_name: str) -> tuple[float, dict[str, float]]:
    text = java_file.read_text(encoding="utf-8", errors="ignore")
    ranges = find_method_ranges(text, method_name)
    if ranges:
        lines = text.splitlines()
        start = max(ranges[0].start - 1, 0)
        end = min(ranges[0].end, len(lines))
        body = "\n".join(lines[start:end])
    else:
        body = text

    signature = method_signature_fragment(body, method_name)
    parameter_count = count_parameters(signature)
    external_calls = len(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\.\s*[A-Za-z_][A-Za-z0-9_]*\s*\(", body))
    dependency_mentions = len(set(re.findall(r"\b(?:new\s+)?([A-Z][A-Za-z0-9_]{2,})\b", body)))
    control_flow = len(re.findall(r"\b(if|for|while|switch|case|catch)\b|&&|\|\|", body))
    throws_or_catches = len(re.findall(r"\b(throw|throws|catch)\b", body))
    constructors_or_types = len(re.findall(r"\bnew\s+[A-Z][A-Za-z0-9_]*\s*\(", body))

    breakdown = {
        "E": min(external_calls / 3.0, 3.0),
        "D": min(dependency_mentions / 4.0, 3.0),
        "C": min(control_flow / 3.0, 3.0),
        "P": min(parameter_count / 3.0, 3.0),
        "T": min(throws_or_catches / 2.0, 3.0),
        "CT": min(constructors_or_types / 2.0, 3.0),
    }
    score = (
        0.3 * breakdown["E"]
        + 0.3 * breakdown["D"]
        + 0.1 * breakdown["C"]
        + 0.05 * breakdown["P"]
        + 0.15 * breakdown["T"]
        + 0.1 * breakdown["CT"]
    )
    return round(score, 4), breakdown


def method_signature_fragment(body: str, method_name: str) -> str:
    match = re.search(rf"\b{re.escape(method_name)}\s*\(([^)]*)\)", body)
    return match.group(1) if match else ""


def count_parameters(signature_fragment: str) -> int:
    if not signature_fragment.strip():
        return 0
    return len([part for part in signature_fragment.split(",") if part.strip()])


def select_methods(
    projects: list[ProjectSpec],
    candidates: list[dict],
    threshold: float = MDCI_THRESHOLD,
    allow_fill: bool = False,
) -> list[dict]:
    selected: list[dict] = []
    by_project: dict[str, list[dict]] = {}
    for item in candidates:
        by_project.setdefault(item["project_id"], []).append(item)

    for project in projects:
        project_candidates = sorted(
            by_project.get(project.project_id, []),
            key=lambda item: (-float(item["mdci"]), -float(item["dcci"]), item["id"]),
        )
        eligible = [item for item in project_candidates if float(item["mdci"]) >= threshold]
        chosen = eligible[: project.target_methods]
        if len(chosen) < project.target_methods and allow_fill:
            seen = {item["id"] for item in chosen}
            for item in project_candidates:
                if item["id"] not in seen:
                    clone = dict(item)
                    clone["selection_note"] = f"below MDCI threshold fill: {clone['mdci']} < {threshold}"
                    chosen.append(clone)
                    seen.add(item["id"])
                if len(chosen) >= project.target_methods:
                    break
        if len(chosen) < project.target_methods:
            raise ValueError(
                f"{project.project_id} has {len(chosen)}/{project.target_methods} methods with MDCI >= {threshold}. "
                "Rerun with --allow-fill only if you want explicitly labeled fallback rows."
            )
        for item in chosen[: project.target_methods]:
            selected.append({**item, "selection_source": "maco-aligned-mdci-heuristic"})
    return selected


def unique_focal_classes(methods: Iterable[dict]) -> list[dict]:
    by_class: dict[tuple[str, str], dict] = {}
    for item in methods:
        key = (str(item["project_id"]), str(item.get("fqcn") or item.get("class_name") or ""))
        by_class.setdefault(key, item)
    return [by_class[key] for key in sorted(by_class)]


def evosuite_command(
    evosuite_jar: Path,
    project_root: Path,
    fqcn: str,
    output_dir: Path,
    classpath_extra: str = "",
    search_budget: int = 60,
    classpath_entries: list[Path] | None = None,
) -> list[str]:
    discovered = classpath_entries if classpath_entries is not None else discover_classpath_entries(project_root)
    if not discovered:
        discovered = [project_root / "target" / "classes"]
    classpath_parts = [str(path) for path in discovered]
    if classpath_extra:
        classpath_parts.append(classpath_extra)
    return [
        "java",
        "-jar",
        str(evosuite_jar),
        "-class",
        fqcn,
        "-projectCP",
        os.pathsep.join(classpath_parts),
        "-Dtest_dir=" + str(output_dir.resolve()),
        "-Dsearch_budget=" + str(search_budget),
    ]


def run_evosuite_baseline(
    methods: list[dict],
    projects_root: Path,
    evosuite_jar: Path,
    output_dir: Path,
    timeout: int,
    dry_run: bool,
    search_budget: int,
    classpath_extra: str = "",
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for item in unique_focal_classes(methods):
        project = str(item["project_id"])
        fqcn = str(item.get("fqcn") or item.get("class_name") or "")
        if not fqcn:
            rows.append(evosuite_row(item, "missing_fqcn", "", "", ""))
            continue
        project_root = project_dir(projects_root, ProjectSpec(project, project, "", 0, 0, "", [], [], []))
        class_output_dir = output_dir / project / fqcn
        cmd = evosuite_command(
            evosuite_jar,
            project_root,
            fqcn,
            class_output_dir,
            classpath_extra=classpath_extra,
            search_budget=search_budget,
        )
        log_file = output_dir / project / f"{safe_name(fqcn)}.evosuite.log"
        if dry_run:
            rows.append(evosuite_row(item, "planned", cmd, "", log_file))
            continue
        log_file.parent.mkdir(parents=True, exist_ok=True)
        status, return_code, output = run_command(cmd, project_root, timeout)
        write_log(log_file, output)
        rows.append(evosuite_row(item, status, cmd, return_code, log_file))
    return rows


def evosuite_row(item: dict, status: str, command: list[str] | str, return_code: int | str, log_file: Path | str) -> dict:
    return {
        "project_id": item.get("project_id", ""),
        "fqcn": item.get("fqcn", item.get("class_name", "")),
        "status": status,
        "command": " ".join(command) if isinstance(command, list) else command,
        "return_code": return_code,
        "log_file": str(log_file),
    }


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def write_table(rows: list[dict], output_dir: Path, stem: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    write_markdown_table(rows, fields, md_path)


def write_markdown_table(rows: list[dict], fields: list[str], output_path: Path):
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join(["---"] * len(fields)) + " |",
    ]
    for row in rows:
        values = [str(row.get(field, "")).replace("|", "\\|") for field in fields]
        lines.append("| " + " | ".join(values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_log(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def append_log(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(text)


def read_json_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array: {path}")
    return data


def write_selection_evidence(selected: list[dict], projects: list[ProjectSpec], output_dir: Path):
    by_project = {project.project_id: project for project in projects}
    rows = []
    for project_id in sorted(by_project):
        project = by_project[project_id]
        project_rows = [item for item in selected if item["project_id"] == project_id]
        rows.append(
            {
                "project_id": project_id,
                "target_methods": project.target_methods,
                "selected_methods": len(project_rows),
                "mdci_ge_1": sum(1 for item in project_rows if float(item["mdci"]) >= MDCI_THRESHOLD),
                "below_threshold_fill": sum(1 for item in project_rows if "selection_note" in item),
            }
        )
    write_table(rows, output_dir, "maco_aligned_41_selection_evidence")


def command_checkout(args):
    projects = load_projects(Path(args.manifest))
    projects_root = Path(args.projects_root)
    projects_root.mkdir(parents=True, exist_ok=True)
    rows = checkout_projects(projects, projects_root, Path(args.output_dir), args.timeout)
    write_table(rows, Path(args.output_dir), "checkout_summary")


def command_build(args):
    projects = load_projects(Path(args.manifest))
    rows = buildability_check(projects, Path(args.projects_root), Path(args.output_dir), args.timeout)
    write_table(rows, Path(args.output_dir), "buildability_summary")
    passed = sum(1 for row in rows if row["status"] == "ok")
    print(f"Buildability pass rate: {passed}/{len(rows)} ({format_rate(passed, len(rows))})")


def command_collect(args):
    projects = load_projects(Path(args.manifest))
    output_dir = Path(args.output_dir)
    candidates = collect_candidates(projects, Path(args.projects_root), skip_errors=not args.no_skip_errors)
    write_table(candidates, output_dir, "maco_aligned_candidates")
    selected = select_methods(projects, candidates, threshold=args.min_mdci, allow_fill=args.allow_fill)
    method_list_path = Path(args.method_list_output)
    method_list_path.parent.mkdir(parents=True, exist_ok=True)
    method_list_path.write_text(json.dumps(selected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_selection_evidence(selected, projects, output_dir)
    print(f"Wrote {len(candidates)} candidates and {len(selected)} selected focal methods")


def command_evosuite(args):
    methods = read_json_list(Path(args.method_list))
    rows = run_evosuite_baseline(
        methods,
        Path(args.projects_root),
        Path(args.evosuite_jar),
        Path(args.output_dir),
        timeout=args.timeout,
        dry_run=args.dry_run,
        search_budget=args.search_budget,
        classpath_extra=args.classpath_extra,
    )
    write_table(rows, Path(args.output_dir), "evosuite_baseline_summary")
    planned_or_ok = sum(1 for row in rows if row["status"] in {"planned", "ok"})
    print(f"EvoSuite class generation status: {planned_or_ok}/{len(rows)} ({format_rate(planned_or_ok, len(rows))})")


def command_focal_evaluate(args):
    source_root = Path(args.source_root) if args.source_root else None
    focal_methods = load_focal_methods(Path(args.method_list), source_root, args.prefix_map)
    approaches = [(name, load_coverage_xmls(root)) for name, root in args.approach]
    write_outputs(focal_methods, approaches, Path(args.output_dir))
    print(f"Wrote MACO-aligned focal-method coverage outputs under {args.output_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MACO-aligned 41 Stage B tools")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="MACO-aligned project manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    checkout = subparsers.add_parser("checkout-projects", help="Clone and checkout Stage B projects")
    checkout.add_argument("--projects-root", required=True, help="Directory that will contain project checkouts")
    checkout.add_argument("--output-dir", required=True, help="Directory for checkout evidence")
    checkout.add_argument("--timeout", type=int, default=600, help="Timeout per git command")
    checkout.set_defaults(func=command_checkout)

    build = subparsers.add_parser("buildability-check", help="Run configured build commands")
    build.add_argument("--projects-root", required=True, help="Directory containing project checkouts")
    build.add_argument("--output-dir", required=True, help="Directory for buildability evidence")
    build.add_argument("--timeout", type=int, default=900, help="Timeout per build command")
    build.set_defaults(func=command_build)

    collect = subparsers.add_parser("collect-method-list", help="Collect candidates and write MACO-aligned method list")
    collect.add_argument("--projects-root", required=True, help="Directory containing project checkouts")
    collect.add_argument("--output-dir", required=True, help="Directory for candidate/selection evidence")
    collect.add_argument(
        "--method-list-output",
        default="experiments/method_lists/maco_aligned_41.json",
        help="Selected method-list output JSON",
    )
    collect.add_argument("--min-mdci", type=float, default=MDCI_THRESHOLD, help="Minimum MDCI threshold")
    collect.add_argument("--allow-fill", action="store_true", help="Fill quotas below threshold with explicit notes")
    collect.add_argument("--no-skip-errors", action="store_true", help="Fail on DCCI/parser errors")
    collect.set_defaults(func=command_collect)

    evosuite = subparsers.add_parser("evosuite-baseline", help="Run or plan EvoSuite generation per target class")
    evosuite.add_argument("--method-list", required=True, help="MACO-aligned method list")
    evosuite.add_argument("--projects-root", required=True, help="Directory containing project checkouts")
    evosuite.add_argument("--evosuite-jar", required=True, help="Path to evosuite-standalone jar")
    evosuite.add_argument("--output-dir", required=True, help="Directory for EvoSuite generated tests and evidence")
    evosuite.add_argument("--timeout", type=int, default=900, help="Timeout per target class")
    evosuite.add_argument("--search-budget", type=int, default=60, help="EvoSuite search budget per target class")
    evosuite.add_argument(
        "--classpath-extra",
        default="",
        help="Additional classpath entries for EvoSuite, joined using the platform path separator",
    )
    evosuite.add_argument("--dry-run", action="store_true", help="Write planned commands without executing EvoSuite")
    evosuite.set_defaults(func=command_evosuite)

    focal = subparsers.add_parser("focal-evaluate", help="Compute focal-method coverage from preserved XML reports")
    focal.add_argument("--method-list", required=True, help="MACO-aligned method list")
    focal.add_argument("--source-root", default="", help="Source root used when method targets are from another host")
    focal.add_argument("--prefix-map", action="append", default=[], type=parse_prefix_map, help="Map OLD=NEW target prefixes")
    focal.add_argument("--approach", action="append", required=True, type=parse_approach, help="Approach XML root, NAME=PATH")
    focal.add_argument("--output-dir", required=True, help="Output directory for focal-method coverage tables")
    focal.set_defaults(func=command_focal_evaluate)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
