"""Exact probe-union scoring for each new opt-in coverage-feedback round."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from scripts.merge_kcf_execution_coverage import resolve_executions, merge_accepted_coverage
from scripts.build_kcf_coverage_reference import digest


def write_index(root, entries):
    (root / "accepted_xml_index.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def execution_fields(xml):
    xml = Path(xml).resolve()
    execution = xml.parent.parent
    return {"execution_xml": str(xml), "execution_exec_sha256": digest(execution / "jacoco.exec"),
            "execution_junit_sha256": digest(execution / "junit.log")}


def validate_exact_mode(args):
    if not getattr(args, "exact_exec_union", False):
        return
    if not args.passing_only:
        raise ValueError("Exact per-round scoring requires --passing-only")
    if not args.exact_reference_root or not args.seed_execution_roots:
        raise ValueError("Exact scoring requires reference root and original seed execution roots")
    reference = Path(args.exact_reference_root).resolve()
    if Path(args.reference_xml_root or "").resolve() != reference / "xml":
        raise ValueError("Reference XML root must equal exact reference root/xml")
    if not (reference / "reference_manifest.json").is_file():
        raise ValueError("Missing frozen reference manifest")
    if any(not Path(root).is_dir() for root in args.seed_execution_roots):
        raise ValueError("Missing original seed execution root")


def prepare_seed_index(raw_root, accepted, methods, execution_roots):
    records = resolve_executions(raw_root, methods, execution_roots)
    by_name = {r["accepted_xml_name"]: r for r in records}
    entries = json.loads((raw_root / "accepted_xml_index.json").read_text(encoding="utf-8"))
    accepted.mkdir(parents=True, exist_ok=False)
    frozen = []
    for entry in entries:
        record = by_name[entry["xml_name"]]
        shutil.copy2(raw_root / entry["xml_name"], accepted / entry["xml_name"])
        frozen.append({**entry, **execution_fields(record["xml_file"])})
    write_index(accepted, frozen)


def accept_incremental(accepted, result, identity, round_index):
    if result.get("status") != "ok" or result.get("semantic_review_required", False):
        raise ValueError("Only accepted passing executions can contribute probes")
    xml = Path(result["xml_file"]).resolve()
    name = f"round{round_index}__{identity}.xml"
    if Path(name).name != name or (accepted / name).exists():
        raise ValueError("Invalid or duplicate round suite identity")
    entries = json.loads((accepted / "accepted_xml_index.json").read_text(encoding="utf-8"))
    fields = execution_fields(xml)
    entry = {"id": identity, "status": "ok", "xml_name": name, "xml_sha256": digest(xml),
             "semantic_review_required": False,
             "origin": result.get("acceptance_origin", "passing_initial_incremental_suite"), **fields}
    shutil.copy2(xml, accepted / name)
    entries.append(entry)
    write_index(accepted, entries)


def evaluate_round(args, output_root, method_list, round_index):
    merge_args = SimpleNamespace(
        method_list=Path(method_list).resolve(), accepted_xml_root=output_root / "probe_accepted_xml",
        execution_roots=[Path(root).resolve() for root in args.seed_execution_roots] + [output_root / "incremental_jacoco"],
        reference_root=Path(args.exact_reference_root).resolve(), projects_root=Path(args.projects_root).resolve(),
        jacoco_cli=Path(args.jacoco_cli).resolve(), java="java", approach_name=args.approach_name,
        output_dir=output_root / f"probe_union_round{round_index}",
        evaluation_dir=output_root / f"coverage_round{round_index}")
    return merge_accepted_coverage(merge_args)
