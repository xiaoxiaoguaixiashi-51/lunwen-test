"""Create a fixed focal denominator from compiled classes without generated tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_focal_method_coverage import load_focal_methods, load_coverage_xmls, write_outputs


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--jacoco-cli", type=Path, required=True)
    parser.add_argument("--java", default="java")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Use a new directory for a frozen coverage reference")
    args.output_dir.mkdir(parents=True)
    methods = json.loads(args.method_list.read_text(encoding="utf-8"))
    if len(methods) != 41 or len({r["id"] for r in methods}) != 41:
        raise ValueError("Expected 41 fixed focal IDs")
    records = []
    for project_id in sorted({row["project_id"] for row in methods}):
        root = args.projects_root / project_id
        classes = root / ("build/core" if project_id == "jdom2" else "target/classes")
        class_files = sorted(classes.rglob("*.class"))
        if not class_files:
            raise ValueError(f"No compiled main classes: {project_id}")
        xml = args.output_dir / "xml" / project_id / "jacoco.xml"
        xml.parent.mkdir(parents=True)
        command = [args.java, "-jar", str(args.jacoco_cli), "report", "--classfiles", str(classes),
                   "--xml", str(xml)]
        # JaCoCo report accepts no exec files; all compiled lines are then missed.
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (xml.parent / "report.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"JaCoCo reference failed for {project_id}: {result.stderr[-1500:]}")
        class_hashes = {str(p.relative_to(classes)): digest(p) for p in class_files}
        records.append({"project_id": project_id, "class_files": len(class_files),
                        "class_tree_sha256": hashlib.sha256(json.dumps(class_hashes, sort_keys=True).encode()).hexdigest(),
                        "xml_sha256": digest(xml), "command": command})
    focal = load_focal_methods(args.method_list, None, [])
    coverage = load_coverage_xmls(args.output_dir / "xml")
    write_outputs(focal, [("Reference", {})], args.output_dir / "evaluation", reference=coverage)
    record = {"method_list_sha256": digest(args.method_list), "jacoco_cli_sha256": digest(args.jacoco_cli),
              "projects": records, "kind": "compiled_classes_zero_execution_reference"}
    (args.output_dir / "reference_manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print((args.output_dir / "evaluation/focal_method_coverage_summary.json").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
