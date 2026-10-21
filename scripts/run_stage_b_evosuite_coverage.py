"""Compile, run, and collect JaCoCo XML for Stage B EvoSuite tests.

This runner consumes the EvoSuite generation output from ``maco_stage_b.py``.
It patches EvoSuite's generated ``separateClassLoader = true`` annotation to
``false`` in a copied work directory so JaCoCo can observe the project classes.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maco_stage_b import discover_classpath_entries, safe_name, write_table


def run(command: list[str], cwd: Path, timeout: int) -> tuple[str, int, str]:
    try:
        proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        return ("ok" if proc.returncode == 0 else "failed"), proc.returncode, output
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return "timeout", -1, stdout + stderr + "\nTIMEOUT\n"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def project_dir(projects_root: Path, project_id: str) -> Path:
    return projects_root / project_id


def dependency_classpath(project_root: Path, output_dir: Path, timeout: int) -> str:
    if not (project_root / "pom.xml").exists():
        return ""
    cp_file = output_dir / "maven.classpath.txt"
    status, _code, output = run(
        ["mvn", "-q", "dependency:build-classpath", f"-Dmdep.outputFile={cp_file}"],
        project_root,
        timeout,
    )
    (output_dir / "maven.classpath.log").write_text(output, encoding="utf-8")
    if status != "ok" or not cp_file.exists():
        return ""
    return cp_file.read_text(encoding="utf-8").strip()


def junit_classpath() -> list[str]:
    candidates = [
        Path("/root/.m2/repository/junit/junit/4.13.2/junit-4.13.2.jar"),
        Path("/root/.m2/repository/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"),
        Path("/root/.m2/repository/org/hamcrest/hamcrest/2.2/hamcrest-2.2.jar"),
    ]
    return [str(path) for path in candidates if path.exists()]


def copy_and_patch_sources(source_dir: Path, work_src: Path):
    if work_src.exists():
        shutil.rmtree(work_src)
    shutil.copytree(source_dir, work_src)
    for java_file in work_src.rglob("*.java"):
        text = java_file.read_text(encoding="utf-8", errors="replace")
        text = text.replace("separateClassLoader = true", "separateClassLoader = false")
        java_file.write_text(text, encoding="utf-8")


def find_generated_test(work_src: Path) -> tuple[str, list[Path]]:
    java_files = sorted(work_src.rglob("*.java"))
    test_files = [path for path in java_files if path.name.endswith("_ESTest.java")]
    if not test_files:
        raise ValueError(f"No *_ESTest.java under {work_src}")
    test_file = test_files[0]
    package = ""
    for line in test_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("package ") and stripped.endswith(";"):
            package = stripped[len("package ") : -1].strip()
            break
    class_name = test_file.stem
    return (f"{package}.{class_name}" if package else class_name), java_files


def report_xml_has_lines(xml_path: Path) -> bool:
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return False
    return any(True for _ in root.findall(".//line"))


def run_one(row: dict, args, cp_cache: dict[str, str]) -> dict:
    project_id = row["project_id"]
    fqcn = row["fqcn"]
    project_root = project_dir(Path(args.projects_root), project_id)
    source_dir = Path(args.evosuite_dir).resolve() / project_id / safe_name(fqcn)
    out_dir = Path(args.output_dir).resolve() / project_id / safe_name(fqcn)
    work_src = out_dir / "src"
    classes_dir = out_dir / "classes"
    xml_dir = out_dir / "xml"
    out_dir.mkdir(parents=True, exist_ok=True)
    classes_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "project_id": project_id,
        "fqcn": fqcn,
        "source_dir": str(source_dir),
        "output_dir": str(out_dir),
    }
    if row.get("status") != "ok":
        return {**base, "status": "generation_" + row.get("status", "missing"), "test_class": "", "xml_file": ""}
    if not source_dir.exists():
        return {**base, "status": "missing_generated_tests", "test_class": "", "xml_file": ""}

    copy_and_patch_sources(source_dir, work_src)
    test_class, java_files = find_generated_test(work_src)
    source_list = out_dir / "sources.txt"
    source_list.write_text("\n".join(str(path) for path in java_files) + "\n", encoding="utf-8")

    discovered_cp = [str(path) for path in discover_classpath_entries(project_root)]
    dep_cp = cp_cache.setdefault(project_id, dependency_classpath(project_root, out_dir, args.timeout))
    cp_parts = discovered_cp + ([dep_cp] if dep_cp else []) + [args.evosuite_jar] + junit_classpath()
    classpath = os.pathsep.join(part for part in cp_parts if part)

    compile_cmd = [
        "javac",
        "-source",
        "1.8",
        "-target",
        "1.8",
        "-cp",
        classpath,
        "-d",
        str(classes_dir),
        "@" + str(source_list),
    ]
    compile_status, compile_code, compile_output = run(compile_cmd, project_root, args.timeout)
    (out_dir / "compile.log").write_text(compile_output, encoding="utf-8")
    if compile_status != "ok":
        return {
            **base,
            "status": "compile_" + compile_status,
            "compile_code": compile_code,
            "test_code": "",
            "xml_code": "",
            "test_class": test_class,
            "xml_file": "",
        }

    exec_file = out_dir / "jacoco.exec"
    run_cp = os.pathsep.join([str(classes_dir), classpath])
    test_cmd = [
        "java",
        f"-javaagent:{args.jacoco_agent}=destfile={exec_file}",
        "-cp",
        run_cp,
        "org.junit.runner.JUnitCore",
        test_class,
    ]
    test_status, test_code, test_output = run(test_cmd, project_root, args.timeout)
    (out_dir / "junit.log").write_text(test_output, encoding="utf-8")

    xml_file = xml_dir / "jacoco.xml"
    report_cmd = ["java", "-jar", args.jacoco_cli, "report", str(exec_file)]
    for class_dir in discovered_cp:
        report_cmd.extend(["--classfiles", class_dir])
    for source_root in ["src/main/java", "core/src/java", "src/java"]:
        candidate = project_root / source_root
        if candidate.exists():
            report_cmd.extend(["--sourcefiles", str(candidate)])
    report_cmd.extend(["--xml", str(xml_file)])
    xml_status, xml_code, xml_output = run(report_cmd, project_root, args.timeout)
    (out_dir / "jacoco_report.log").write_text(xml_output, encoding="utf-8")

    status = "ok" if test_status == "ok" and xml_status == "ok" and report_xml_has_lines(xml_file) else "test_" + test_status
    if xml_status != "ok" or not report_xml_has_lines(xml_file):
        status = "coverage_" + xml_status
    return {
        **base,
        "status": status,
        "compile_code": compile_code,
        "test_code": test_code,
        "xml_code": xml_code,
        "test_class": test_class,
        "xml_file": str(xml_file) if xml_file.exists() else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Run Stage B EvoSuite tests with JaCoCo XML coverage")
    parser.add_argument("--evosuite-summary", required=True)
    parser.add_argument("--evosuite-dir", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evosuite-jar", default="/root/tools/evosuite.jar")
    parser.add_argument("--jacoco-agent", default="/root/tools/jacocoagent.jar")
    parser.add_argument("--jacoco-cli", default="/root/tools/jacococli.jar")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    rows = []
    cp_cache: dict[str, str] = {}
    for row in read_rows(Path(args.evosuite_summary)):
        rows.append(run_one(row, args, cp_cache))
    write_table(rows, Path(args.output_dir), "evosuite_jacoco_summary")
    ok = sum(1 for row in rows if row["status"] == "ok")
    print(f"EvoSuite JaCoCo run status: {ok}/{len(rows)}")


if __name__ == "__main__":
    main()
