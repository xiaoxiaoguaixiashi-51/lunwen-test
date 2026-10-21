"""Validate a KCF-UTG host before any model calls are made."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_preflight(
    method_list: Path,
    projects_root: Path,
    knowledge_path: Path,
    expected_method_count: int = 41,
) -> dict:
    methods = load_json(method_list)
    errors: list[str] = []
    warnings: list[str] = []
    ids = [item.get("id") for item in methods]
    if len(methods) != expected_method_count or len(set(ids)) != expected_method_count:
        errors.append(
            f"expected {expected_method_count} unique methods, "
            f"got {len(methods)} rows/{len(set(ids))} ids"
        )

    projects = sorted({item.get("project_id", "") for item in methods})
    missing_targets = []
    missing_projects = []
    for project_id in projects:
        if not (projects_root / project_id).is_dir():
            missing_projects.append(project_id)
    for item in methods:
        target = Path(item.get("target", ""))
        if not target.is_file():
            rebased = projects_root / item["project_id"] / item.get("target_relative", "")
            if not rebased.is_file():
                missing_targets.append(item.get("id", ""))
    if missing_projects:
        errors.append("missing project directories: " + ", ".join(missing_projects))
    if missing_targets:
        errors.append(f"missing target source files: {len(missing_targets)}")
    if not knowledge_path.is_file():
        errors.append(f"knowledge file not found: {knowledge_path}")
    if not any(item.get("project_id") == "windward" for item in methods):
        warnings.append("windward target is absent from method list")

    return {
        "ok": not errors,
        "method_count": len(methods),
        "project_ids": projects,
        "missing_projects": missing_projects,
        "missing_target_ids": missing_targets,
        "knowledge_exists": knowledge_path.is_file(),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--knowledge-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_preflight(args.method_list, args.projects_root, args.knowledge_path)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    print(text, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
