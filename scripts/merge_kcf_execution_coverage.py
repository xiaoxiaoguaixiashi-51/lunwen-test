"""Recompute accepted-suite coverage by merging JaCoCo probes, never XML counts.

Offline post-processing only: does not generate tests or change previous scores.
Execution roots must contain isolated suite runs (xml/jacoco.xml, jacoco.exec,
junit.log). Ambiguous provenance is rejected, not resolved by path order.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_focal_method_coverage import load_focal_methods, load_coverage_xmls, write_outputs
from scripts.build_kcf_coverage_reference import digest
from scripts.summarize_kcf_pilot import junit_counts


def class_tree_hash(classes):
    hashes = {str(path.relative_to(classes)): digest(path) for path in sorted(classes.rglob("*.class"))}
    if not hashes:
        raise ValueError(f"No compiled classes: {classes}")
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def resolve_executions(accepted, methods, roots):
    entries = json.loads((accepted / "accepted_xml_index.json").read_text(encoding="utf-8"))
    names = [entry["xml_name"] for entry in entries]
    if len(names) != len(set(names)) or set(names) != {p.name for p in accepted.rglob("*.xml")}:
        raise ValueError("Accepted XML set is not closed and unique")
    candidates = {}
    for root in roots:
        for xml in root.rglob("xml/jacoco.xml"):
            execution = xml.parent.parent
            if (execution / "jacoco.exec").is_file() and (execution / "junit.log").is_file():
                candidates.setdefault(digest(xml), set()).add(xml.resolve())
    records = []
    for entry in entries:
        name = entry["xml_name"]
        if Path(name).name != name or entry["id"] not in methods:
            raise ValueError("Invalid accepted suite identity")
        if entry.get("status") != "ok" or entry.get("semantic_review_required") is not False:
            raise ValueError("Unaccepted suite cannot contribute execution data")
        if digest(accepted / name) != entry["xml_sha256"]:
            raise ValueError("Accepted XML hash mismatch")
        matches = candidates.get(entry["xml_sha256"], set())
        if entry.get("execution_xml"):
            explicit = Path(entry["execution_xml"]).resolve()
            if not any(explicit.is_relative_to(Path(root).resolve()) for root in roots):
                raise ValueError("Explicit execution XML outside allowed roots")
            matches = matches & {explicit}
        if len(matches) != 1:
            raise ValueError(f"Require one original isolated execution for {name}; found {len(matches)}")
        xml = next(iter(matches))
        execution = xml.parent.parent
        log = execution / "junit.log"
        counts = junit_counts(log.read_text(encoding="utf-8"))
        if not isinstance(counts["tests_run"], int) or counts["tests_run"] <= 0 or counts["failures"] != 0:
            raise ValueError("Execution is not a positive passing JUnit suite")
        data = execution / "jacoco.exec"
        if not data.stat().st_size:
            raise ValueError("Empty execution data")
        for field, path in (("execution_exec_sha256", data), ("execution_junit_sha256", log)):
            if field in entry and entry[field] != digest(path):
                raise ValueError("Frozen execution evidence changed: " + field)
        records.append({"id": entry["id"], "project_id": methods[entry["id"]]["project_id"],
                        "accepted_xml_name": name, "xml_file": str(xml), "xml_sha256": digest(xml),
                        "exec_file": str(data), "exec_sha256": digest(data), "junit_log": str(log),
                        "junit_log_sha256": digest(log), "junit": counts, "origin": entry["origin"]})
    return records


def check_execution_ids(output):
    """execinfo lists class ID, probe count, and VM class name per execution."""
    ids = {}
    for line in output.splitlines():
        match = re.match(r"\s*([0-9a-fA-F]{16})\s+\d+\s+of\s+\d+\s+(.+?)\s*$", line)
        if match:
            class_id, name = match.groups()
            if name in ids and ids[name] != class_id:
                raise ValueError(f"Different executed class versions: {name}")
            ids[name] = class_id
    if not ids:
        raise ValueError("No class IDs parsed from JaCoCo execinfo")
    return ids


def command(args, log):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    output = (result.stdout or "") + (result.stderr or "")
    log.write_text(output, encoding="utf-8")
    if result.returncode or "does not match" in output.lower() or "do not match" in output.lower():
        raise RuntimeError(f"JaCoCo failed or mismatched class data: {log}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--accepted-xml-root", type=Path, required=True)
    parser.add_argument("--execution-roots", nargs="+", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--jacoco-cli", type=Path, required=True)
    parser.add_argument("--java", default="java")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--approach-name", default="Exact_exec_union")
    args = parser.parse_args()
    print(json.dumps(merge_accepted_coverage(args), indent=2))


def merge_accepted_coverage(args):
    """Shared implementation for offline recomputation and feedback round scoring."""
    if args.output_dir.exists():
        raise FileExistsError("Preserve previous results: use a new output directory")
    items = json.loads(args.method_list.read_text(encoding="utf-8"))
    methods = {item["id"]: item for item in items}
    if len(methods) != len(items):
        raise ValueError("Duplicate target IDs")
    reference = json.loads((args.reference_root / "reference_manifest.json").read_text(encoding="utf-8"))
    if digest(args.jacoco_cli) != reference["jacoco_cli_sha256"]:
        raise ValueError("JaCoCo tool differs from frozen reference")
    project_refs = {row["project_id"]: row for row in reference["projects"]}
    # Allow a development subset, but require every selected source to remain frozen.
    for item in items:
        if digest(Path(item["target"])) != item["source_sha256"]:
            raise ValueError("Frozen target source changed")
    records = resolve_executions(args.accepted_xml_root, methods, args.execution_roots)
    for project in {item["project_id"] for item in items}:
        classes = args.projects_root / project / ("build/core" if project == "jdom2" else "target/classes")
        if class_tree_hash(classes) != project_refs[project]["class_tree_sha256"]:
            raise ValueError(f"Compiled classes differ from reference: {project}")
        if digest(args.reference_root / "xml" / project / "jacoco.xml") != project_refs[project]["xml_sha256"]:
            raise ValueError("Frozen reference XML changed")
    args.output_dir.mkdir(parents=True)
    prefix = [args.java, "-jar", str(args.jacoco_cli)]
    for project in sorted({item["project_id"] for item in items}):
        folder = args.output_dir / "xml" / project
        folder.mkdir(parents=True)
        files = sorted({row["exec_file"] for row in records if row["project_id"] == project})
        classes = args.projects_root / project / ("build/core" if project == "jdom2" else "target/classes")
        if files:
            check_execution_ids(command(prefix + ["execinfo"] + files, folder / "execinfo.log"))
            merged = folder / "merged.exec"
            command(prefix + ["merge"] + files + ["--destfile", str(merged)], folder / "merge.log")
        command(prefix + ["report"] + ([str(merged)] if files else [])
                + ["--classfiles", str(classes), "--xml", str(folder / "jacoco.xml")], folder / "report.log")
    focal = load_focal_methods(args.method_list, None, [])
    baseline = load_coverage_xmls(args.reference_root / "xml")
    evaluation_dir = getattr(args, "evaluation_dir", None) or args.output_dir / "evaluation"
    approach_name = getattr(args, "approach_name", "Exact_exec_union")
    write_outputs(focal, [(approach_name, load_coverage_xmls(args.output_dir / "xml"))],
                  evaluation_dir, reference=baseline)
    manifest = {"kind": "offline_accepted_suite_probe_union_not_new_generation",
                "method_list_sha256": digest(args.method_list), "jacoco_cli_sha256": digest(args.jacoco_cli),
                "accepted_index_sha256": digest(args.accepted_xml_root / "accepted_xml_index.json"),
                "executions": records, "project_reference": reference, "approach_name": approach_name}
    (args.output_dir / "execution_union_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return json.loads((evaluation_dir / "focal_method_coverage_summary.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
