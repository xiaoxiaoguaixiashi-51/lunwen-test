"""Run Stage B Ours Full coverage-feedback incremental generation.

This runner preserves the existing Ours-v3 raw evidence as round 0. It then
uses JaCoCo/focal-method uncovered line and branch gaps to generate additional
JUnit4 tests, runs those tests separately, and evaluates the union of raw and
incremental JaCoCo XML files.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maco_stage_b import discover_classpath_entries, safe_name, write_table
from src.core.llm_client import LLMClient, load_config, trace_target
from src.core.batch_runner import load_method_list
from src.retrieval.dependency_knowledge import (
    DEFAULT_KNOWLEDGE_PATH,
    compact_record,
    load_knowledge_records,
    score_record,
    tokenize,
)
from src.utils.experiment_metadata import write_run_metadata, sha256_file
from src.utils.llm_output import extract_fenced_block
from src.utils.repair_integrity import check_repair_integrity
from src.utils.dependency_declarations import grounded_context
from scripts import probe_union_feedback


SYSTEM_PROMPT = """You are the coverage-feedback generation stage of Ours Full.
Generate one complete, self-contained JUnit 4 test class for the requested Java focal method.

Rules:
1. Use JUnit 4 only: org.junit.Test and org.junit.Assert.*.
2. Do not use Mockito, PowerMock, JUnit 5, Jupiter, or external mocking libraries.
3. Prefer real objects, builders, simple stubs, package-visible helpers, or lightweight fake implementations.
4. Target the uncovered lines/branches described in the coverage feedback.
5. Keep tests compatible with javac -source 1.8 -target 1.8.
6. Output only one complete Java file. Do not include explanations.
"""

UNGUARDED_SYSTEM_PROMPT = """You are the coverage-feedback generation stage.
Generate one Java test class for the requested Java focal method.
Do not add explanations outside the Java code.
"""


USER_PROMPT_TEMPLATE = """## Target
Project: {project_id}
Class: {fqcn}
Method: {method_name}
Package: {package_name}
Round: {round_index}

## Focal Source Range
{line_ranges}

## Coverage Gap
{coverage_gap}

## Uncovered / Weak Source Snippet
```java
{source_snippet}
```

## Retrieved KG/LightRAG Coverage-Gap Knowledge
```json
{retrieved_knowledge}
```

Generate a complete JUnit 4 test class named {test_class_name}. Use package `{package_name}` if the target class has a package.
Focus on additional scenarios that are not already covered. Avoid fragile assertions when the branch can be covered by invoking the method safely.
"""

UNGUARDED_USER_PROMPT_TEMPLATE = """## Target
Project: {project_id}
Class: {fqcn}
Method: {method_name}
Round: {round_index}

## Focal Source Range
{line_ranges}

## Coverage Gap
{coverage_gap}

## Uncovered / Weak Source Snippet
```java
{source_snippet}
```

## Retrieved Knowledge
```json
{retrieved_knowledge}
```

Generate an additional Java test class for this target. Output one complete Java file.
"""


FIX_PROMPT_TEMPLATE = """The generated JUnit 4 test failed during {phase}. Repair it.

## Target
Class: {fqcn}
Method: {method_name}
Package: {package_name}

## Current Test Code
```java
{test_code}
```

## Failure Output
```
{failure_output}
```

## Retrieved KG/LightRAG Failure-Repair Knowledge
```json
{retrieved_knowledge}
```

Return one complete Java file. Keep JUnit 4 only. Do not use Mockito, PowerMock, JUnit 5, or external mocking libraries.
"""

UNGUARDED_FIX_PROMPT_TEMPLATE = """The generated Java test failed during {phase}. Repair it.

## Target
Class: {fqcn}
Method: {method_name}

## Current Test Code
```java
{test_code}
```

## Failure Output
```
{failure_output}
```

## Retrieved Knowledge
```json
{retrieved_knowledge}
```

Return one complete Java file.
"""


def run(command: list[str], cwd: Path, timeout: int) -> tuple[str, int, str]:
    try:
        proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        return ("ok" if proc.returncode == 0 else "failed"), proc.returncode, output
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return "timeout", -1, stdout + stderr + "\nTIMEOUT\n"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8")


def package_from_item(item: dict) -> str:
    if item.get("package"):
        return str(item["package"])
    fqcn = str(item.get("fqcn", ""))
    return fqcn.rsplit(".", 1)[0] if "." in fqcn else ""


def class_short_name(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def class_name_for(method: dict, round_index: int) -> str:
    raw = f"{class_short_name(method['fqcn'])}_{method['method']}_CoverageRound{round_index}Test"
    cleaned = re.sub(r"[^A-Za-z0-9_$]", "_", raw)
    if not re.match(r"[A-Za-z_$]", cleaned):
        cleaned = "Generated" + cleaned
    return cleaned


def read_methods(path: Path) -> list[dict]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("Method list must be a JSON array")
    return data


def parse_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for part in (value or "").split(";"):
        if "-" not in part:
            continue
        left, right = part.split("-", 1)
        try:
            ranges.append((int(left), int(right)))
        except ValueError:
            continue
    return ranges


def source_snippet(target: Path, ranges: str, context: int = 8) -> str:
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    selected: list[str] = []
    seen: set[int] = set()
    for start, end in parse_ranges(ranges):
        lo = max(1, start - context)
        hi = min(len(lines), end + context)
        for number in range(lo, hi + 1):
            if number not in seen:
                selected.append(f"{number}: {lines[number - 1]}")
                seen.add(number)
    if not selected:
        for number, line in enumerate(lines[:160], start=1):
            selected.append(f"{number}: {line}")
    return "\n".join(selected[:260])


def pct(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


def read_detail(detail_csv: Path, approach: str) -> list[dict]:
    with detail_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    line_rate = f"{approach}_line_rate"
    branch_rate = f"{approach}_branch_rate"
    gaps = []
    for row in rows:
        lr = pct(row.get(line_rate, ""))
        br = pct(row.get(branch_rate, ""))
        line_gap = lr is not None and lr < 100.0
        branch_gap = br is not None and br < 100.0
        if line_gap or branch_gap:
            gaps.append(row)
    return gaps


def coverage_gap_text(row: dict, approach: str) -> str:
    return (
        f"Current focal line coverage: {row.get(f'{approach}_lines_covered')}/"
        f"{row.get(f'{approach}_lines_total')} = {row.get(f'{approach}_line_rate')}.\n"
        f"Current focal branch coverage: {row.get(f'{approach}_branches_covered')}/"
        f"{row.get(f'{approach}_branches_total')} = {row.get(f'{approach}_branch_rate')}.\n"
        "Generate incremental tests that target the missing focal-method lines or branches."
    )


def retrieve_for_text(records: list[dict], query: str, max_examples: int) -> list[dict]:
    if not records or max_examples <= 0:
        return []
    query_tokens = tokenize(query)
    scored = []
    dependency_analysis = {"static_analysis": {"class_name": "", "method_name": ""}}
    for record in records:
        score = score_record(record, query_tokens, "", dependency_analysis)
        if score > 0:
            scored.append((score, str(record.get("id", "")), record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [compact_record(record, score) for score, _, record in scored[:max_examples]]


def dependency_classpath(project_root: Path, output_dir: Path, timeout: int) -> str:
    if not (project_root / "pom.xml").exists():
        return ""
    cp_file = output_dir / "maven.classpath.txt"
    status, _code, output = run(
        ["mvn", "-q", "dependency:build-classpath", "-Dmdep.scope=test", f"-Dmdep.outputFile={cp_file}"],
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


def report_xml_has_lines(xml_path: Path) -> bool:
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return False
    return any(True for _ in root.findall(".//line"))


def ensure_package(java_code: str, package_name: str) -> str:
    code = java_code.strip()
    if package_name and not re.search(r"^\s*package\s+", code, re.MULTILINE):
        return f"package {package_name};\n\n{code}\n"
    return code + "\n"


def format_generated_code(java_code: str, package_name: str, args) -> str:
    if args.disable_static_guard:
        return java_code.strip() + "\n"
    return ensure_package(java_code, package_name)


def generate_incremental_test(
    llm: LLMClient,
    method: dict,
    row: dict,
    round_index: int,
    records: list[dict],
    args,
    source_context: str = "",
) -> tuple[str, list[dict]]:
    target = Path(method["target"])
    package_name = package_from_item(method)
    test_class = class_name_for(method, round_index)
    snippet = source_snippet(target, row.get("line_ranges", ""))
    gap = coverage_gap_text(row, args.approach_name)
    query = "\n".join([method["fqcn"], method["method"], gap, snippet])
    retrieved = []
    if not args.disable_coverage_gap_retrieval:
        retrieved = retrieve_for_text(records, query, args.max_knowledge_examples)
    prompt_template = UNGUARDED_USER_PROMPT_TEMPLATE if args.disable_static_guard else USER_PROMPT_TEMPLATE
    system_prompt = UNGUARDED_SYSTEM_PROMPT if args.disable_static_guard else SYSTEM_PROMPT
    user_prompt = prompt_template.format(
        project_id=method["project_id"],
        fqcn=method["fqcn"],
        method_name=method["method"],
        package_name=package_name,
        round_index=round_index,
        line_ranges=row.get("line_ranges", ""),
        coverage_gap=gap,
        source_snippet=snippet,
        retrieved_knowledge=json.dumps(retrieved, indent=2, ensure_ascii=False),
        test_class_name=test_class,
    )
    if source_context:
        user_prompt += "\n\n## Verified source context (partial; omissions are unknown, not absence)\n" + source_context
    response = llm.generate(system_prompt, user_prompt, max_tokens=args.max_tokens)
    return format_generated_code(safe_text(extract_fenced_block(response, "java")), package_name, args), retrieved


def repair_test(
    llm: LLMClient,
    test_code: str,
    method: dict,
    failure_output: str,
    phase: str,
    records: list[dict],
    args,
    source_context: str = "",
) -> tuple[str, list[dict]]:
    package_name = package_from_item(method)
    query = "\n".join([method["fqcn"], method["method"], phase, failure_output[:6000], test_code[:6000]])
    retrieved = []
    if not args.disable_failure_repair_retrieval:
        retrieved = retrieve_for_text(records, query, args.max_knowledge_examples)
    prompt_template = UNGUARDED_FIX_PROMPT_TEMPLATE if args.disable_static_guard else FIX_PROMPT_TEMPLATE
    system_prompt = UNGUARDED_SYSTEM_PROMPT if args.disable_static_guard else SYSTEM_PROMPT
    prompt = prompt_template.format(
        phase=phase,
        fqcn=method["fqcn"],
        method_name=method["method"],
        package_name=package_name,
        test_code=test_code,
        failure_output=failure_output[:10000],
        retrieved_knowledge=json.dumps(retrieved, indent=2, ensure_ascii=False),
    )
    if source_context:
        prompt += "\n\n## Verified source context (partial; omissions are unknown, not absence)\n" + source_context
        prompt += ("\nKeep the test class and every existing @Test method. Do not remove assertions, disable tests, "
                   "add assumptions, or bypass failing paths. Correct an expected value/exception only when justified "
                   "by the supplied implementation. Do not merely copy actual output into expected values.")
    response = llm.generate(system_prompt, prompt, max_tokens=args.max_tokens)
    return format_generated_code(safe_text(extract_fenced_block(response, "java")), package_name, args), retrieved


def write_test_file(test_code: str, source_dir: Path, class_name: str) -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f"{class_name}.java"
    path.write_text(test_code, encoding="utf-8", errors="replace")
    return path


def run_generated_test(method: dict, test_file: Path, test_class: str, round_dir: Path, args, cp_cache: dict[str, str]) -> dict:
    project_root = Path(args.projects_root) / method["project_id"]
    out_dir = round_dir / method["project_id"] / safe_name(f"{method['id']}-{method['fqcn']}")
    classes_dir = out_dir / "classes"
    xml_dir = out_dir / "xml"
    out_dir.mkdir(parents=True, exist_ok=True)
    classes_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)

    discovered_cp = [str(path) for path in discover_classpath_entries(project_root)]
    dep_cp = cp_cache.setdefault(method["project_id"], dependency_classpath(project_root, out_dir, args.timeout))
    cp_parts = discovered_cp + ([dep_cp] if dep_cp else []) + junit_classpath()
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
        str(test_file),
    ]
    compile_status, compile_code, compile_output = run(compile_cmd, project_root, args.timeout)
    (out_dir / "compile.log").write_text(compile_output, encoding="utf-8")
    if compile_status != "ok":
        return {"status": "compile_" + compile_status, "output": compile_output, "test_class": test_class, "xml_file": ""}

    package_name = package_from_item(method)
    fq_test_class = f"{package_name}.{test_class}" if package_name else test_class
    exec_file = out_dir / "jacoco.exec"
    run_cp = os.pathsep.join([str(classes_dir), classpath])
    test_cmd = [
        "java",
        f"-javaagent:{args.jacoco_agent}=destfile={exec_file}" + (
            ",append=false" if getattr(args, "passing_only", False) or getattr(args, "isolate_execution", False) else ""),
        "-cp",
        run_cp,
        "org.junit.runner.JUnitCore",
        fq_test_class,
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
    xml_status, _xml_code, xml_output = run(report_cmd, project_root, args.timeout)
    (out_dir / "jacoco_report.log").write_text(xml_output, encoding="utf-8")

    if xml_status != "ok" or not report_xml_has_lines(xml_file):
        return {"status": "coverage_" + xml_status, "output": xml_output, "test_class": fq_test_class, "xml_file": ""}
    if test_status != "ok":
        return {"status": "test_" + test_status, "output": test_output, "test_class": fq_test_class, "xml_file": str(xml_file)}
    return {"status": "ok", "output": test_output, "test_class": fq_test_class, "xml_file": str(xml_file)}


def copy_raw_xmls(raw_xml_root: Path, combined_root: Path):
    raw_out = combined_root / "round0_raw"
    if raw_out.exists():
        return
    raw_out.mkdir(parents=True, exist_ok=True)
    for index, xml in enumerate(sorted(raw_xml_root.rglob("*.xml")), start=1):
        target = raw_out / f"raw_{index:04d}_{safe_name(xml.parent.name)}.xml"
        shutil.copy2(xml, target)


def include_incremental_xml(result: dict, passing_only: bool) -> bool:
    return bool(result.get("xml_file")) and (not passing_only or (
        result.get("status") == "ok" and not result.get("semantic_review_required")))


def run_initial_generated_test(method, test_file, test_class, execution_dir, args, cp_cache):
    if args.passing_only:
        code = test_file.read_text(encoding="utf-8")
        integrity = check_repair_integrity(code, code)
        write_json(test_file.parent / "attempt_0_integrity.json", integrity)
        if not integrity["ok"]:
            return {"status": "integrity_rejected", "output": str(integrity["errors"]), "xml_file": ""}
    return run_generated_test(method, test_file, test_class, execution_dir, args, cp_cache)


def execution_dir_for(output_root, round_index, attempt, isolated):
    base = Path(output_root) / "incremental_jacoco" / f"round{round_index}"
    return base / f"attempt{attempt}" if isolated else base


def validate_passing_seed_index(raw_root: Path, allowed_ids=None):
    index = read_json(raw_root / "accepted_xml_index.json")
    names = set()
    for entry in index:
        if allowed_ids is not None and entry.get("id") not in allowed_ids:
            raise ValueError("Seed XML target is outside the frozen manifest")
        name = entry["xml_name"]
        if Path(name).name != name or entry["status"] != "ok" or entry.get("semantic_review_required"):
            raise ValueError("Seed XML is not approved passing-suite evidence")
        if sha256_file(raw_root / name) != entry["xml_sha256"]:
            raise ValueError("Passing seed XML hash mismatch")
        if name in names:
            raise ValueError("Duplicate seed XML entry")
        names.add(name)
    if names != {str(path.relative_to(raw_root)) for path in raw_root.rglob("*.xml")}:
        raise ValueError("Seed XML directory differs from its acceptance index")


def evaluate(method_list: Path, xml_root: Path, output_dir: Path, approach_name: str, timeout: int,
             reference_xml_root: str | None = None):
    summary = output_dir / "focal_method_coverage_summary.json"
    detail = output_dir / "focal_method_coverage_detail.csv"
    if summary.exists() and detail.exists():
        if reference_xml_root:
            marker = output_dir / "evaluation_inputs.json"
            expected = {"method_list_sha256": sha256_file(method_list), "reference_xml_sha256": {
                str(p.relative_to(reference_xml_root)): sha256_file(p)
                for p in sorted(Path(reference_xml_root).rglob("*.xml"))
            }}
            if not marker.is_file() or read_json(marker) != expected:
                raise ValueError("Cached evaluation does not match the fixed targets/reference")
        return
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_focal_method_coverage.py"),
        "--method-list",
        str(method_list),
        "--approach",
        f"{approach_name}={xml_root}",
        "--output-dir",
        str(output_dir),
    ]
    if reference_xml_root:
        cmd.extend(["--reference-xml-root", reference_xml_root])
    status, code, output = run(cmd, REPO_ROOT, timeout)
    (output_dir / "evaluate.log").write_text(output, encoding="utf-8")
    if status != "ok":
        raise RuntimeError(f"focal coverage evaluation failed: {output[-2000:]}")
    if reference_xml_root:
        write_json(output_dir / "evaluation_inputs.json", {
            "method_list_sha256": sha256_file(method_list), "reference_xml_sha256": {
                str(p.relative_to(reference_xml_root)): sha256_file(p)
                for p in sorted(Path(reference_xml_root).rglob("*.xml"))
            },
        })


def summary_from_output(output_dir: Path) -> dict:
    data = read_json(output_dir / "focal_method_coverage_summary.json")
    return data[0] if data else {}


def main():
    parser = argparse.ArgumentParser(description="Run Ours Full coverage-feedback incremental generation")
    parser.add_argument("--method-list", required=True)
    parser.add_argument("--reference-xml-root", help="Fixed denominator XML, required for owner/signature manifests")
    parser.add_argument("--raw-xml-root", required=True, help="Ours-v3 raw JaCoCo XML root")
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--knowledge-path", default=str(DEFAULT_KNOWLEDGE_PATH))
    parser.add_argument("--approach-name", default="Ours_Full")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--max-methods", type=int, default=0, help="Limit gap methods per round for smoke/debug")
    parser.add_argument("--max-knowledge-examples", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--repair-iterations", type=int, default=1)
    parser.add_argument("--passing-only", action="store_true", help="Require approved passing seed XML and exclude failing incremental suites")
    parser.add_argument("--exact-exec-union", action="store_true", help="Use true exec probe union for every feedback round")
    parser.add_argument("--exact-reference-root", help="Frozen reference root containing reference_manifest.json and xml/")
    parser.add_argument("--seed-execution-roots", nargs="+", help="Original isolated execution roots for the approved seeds")
    parser.add_argument(
        "--disable-coverage-gap-retrieval",
        action="store_true",
        help="Ablation switch: do not retrieve KG/LightRAG records for coverage-gap incremental generation.",
    )
    parser.add_argument(
        "--disable-failure-repair-retrieval",
        action="store_true",
        help="Ablation switch: do not retrieve KG/LightRAG records for compile/runtime failure repair.",
    )
    parser.add_argument(
        "--disable-static-guard",
        action="store_true",
        help="Ablation switch: use weak prompts and disable package post-processing.",
    )
    parser.add_argument("--jacoco-agent", default="/root/tools/jacocoagent.jar")
    parser.add_argument("--jacoco-cli", default="/root/tools/jacococli.jar")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    probe_union_feedback.validate_exact_mode(args)
    os.environ.setdefault("KCF_LLM_TRACE_PATH", str(Path(args.output_dir).resolve() / "llm_calls.jsonl"))
    os.environ.setdefault("KCF_EXPERIMENT_STAGE", "coverage_feedback")

    method_list = Path(args.method_list)
    methods = {item["id"]: item for item in read_methods(method_list)}
    if any(item.get("method_owner") for item in methods.values()) and not args.reference_xml_root:
        raise ValueError("Owner/signature targets require --reference-xml-root before any model call")
    if args.passing_only:
        load_method_list(args.method_list)  # Verify source hashes before model requests.
        validate_passing_seed_index(Path(args.raw_xml_root), methods.keys())
        if Path(args.output_dir).exists():
            raise FileExistsError("Passing-only runs require a fresh output directory; do not reuse legacy XML caches")
    output_root = Path(args.output_dir).resolve()
    combined_xml = output_root / "combined_xml"
    combined_xml.mkdir(parents=True, exist_ok=True)
    records = load_knowledge_records(args.knowledge_path)
    config = load_config(args.config)
    write_run_metadata(
        output_root,
        stage="coverage_feedback",
        method_list=method_list,
        config_path=args.config,
        config=config,
        knowledge_path=args.knowledge_path,
        settings={
            "approach_name": args.approach_name,
            "method_count": len(methods),
            "knowledge_record_count": len(records),
            "knowledge_retrieval_enabled": not (
                args.disable_coverage_gap_retrieval and args.disable_failure_repair_retrieval
            ),
            "coverage_gap_retrieval_enabled": not args.disable_coverage_gap_retrieval,
            "failure_repair_retrieval_enabled": not args.disable_failure_repair_retrieval,
            "static_guard_enabled": not args.disable_static_guard,
            "max_rounds": args.max_rounds,
            "max_methods_per_round": args.max_methods,
            "max_knowledge_examples": args.max_knowledge_examples,
            "max_tokens": args.max_tokens,
            "repair_iterations": args.repair_iterations,
            "passing_only": args.passing_only,
            "coverage_aggregation": "exact_exec_probe_union" if args.exact_exec_union else "legacy_xml_max",
            "dependency_declaration_context_enabled": args.passing_only and not args.disable_static_guard,
        },
        inputs={
            "reference_xml_root": args.reference_xml_root,
            "raw_xml_root": str(Path(args.raw_xml_root).resolve()),
            "raw_xml_count": sum(1 for _ in Path(args.raw_xml_root).rglob("*.xml")),
            "projects_root": str(Path(args.projects_root).resolve()),
        },
    )
    llm = None  # Round-zero exact scoring must not initialize a model client.
    cp_cache: dict[str, str] = {}
    all_round_rows: list[dict] = []

    if args.exact_exec_union:
        probe_union_feedback.prepare_seed_index(Path(args.raw_xml_root), output_root / "probe_accepted_xml", methods,
                                                [Path(root) for root in args.seed_execution_roots])
        probe_union_feedback.evaluate_round(args, output_root, method_list, 0)
    else:
        copy_raw_xmls(Path(args.raw_xml_root), combined_xml)
        evaluate(method_list, combined_xml, output_root / "coverage_round0", args.approach_name, args.timeout,
                 args.reference_xml_root)
    previous_summary = summary_from_output(output_root / "coverage_round0")

    for round_index in range(1, args.max_rounds + 1):
        detail = output_root / f"coverage_round{round_index - 1}" / "focal_method_coverage_detail.csv"
        gaps = read_detail(detail, args.approach_name)
        if args.max_methods > 0:
            gaps = gaps[: args.max_methods]
        if not gaps:
            break
        if llm is None:
            llm = LLMClient(config)

        round_rows = []
        for row in gaps:
            method = methods[row["id"]]
            test_class = class_name_for(method, round_index)
            gen_dir = output_root / "generated_tests" / f"round{round_index}" / method["id"]
            status_file = gen_dir / "status.json"
            if status_file.exists():
                status = read_json(status_file)
                round_rows.append(status)
                all_round_rows.append(status)
                continue

            try:
                context = ""
                if args.passing_only:
                    source_info = grounded_context(method, args.projects_root, not args.disable_static_guard)
                    write_json(gen_dir / "source_context.json", source_info)
                    context = source_info["context"]
                with trace_target(method["id"]):
                    test_code, coverage_kg = generate_incremental_test(llm, method, row, round_index, records, args,
                                                                     source_context=context)
                test_file = write_test_file(test_code, gen_dir, test_class)
                retrieval_log = {"coverage-gap": coverage_kg, "failure-repair": []}
                result = run_initial_generated_test(method, test_file, test_class,
                                            execution_dir_for(output_root, round_index, 0, args.passing_only), args, cp_cache)
                (gen_dir / "attempt_0.java.txt").write_text(test_code, encoding="utf-8")
                write_json(gen_dir / "attempt_0.json", {"result": result, "retrieved_knowledge": coverage_kg})
                for repair_index in range(1, args.repair_iterations + 1):
                    if result["status"] in {"ok", "integrity_rejected"}:
                        break
                    with trace_target(method["id"]):
                        repaired, repair_kg = repair_test(llm, test_code, method, result.get("output", ""), result["status"], records, args,
                                                         source_context=context)
                    retrieval_log["failure-repair"].append({"iteration": repair_index, "records": repair_kg})
                    if args.passing_only:
                        integrity = check_repair_integrity(test_code, repaired)
                        write_json(gen_dir / f"attempt_{repair_index}_integrity.json", integrity)
                        if not integrity["ok"]:
                            (gen_dir / f"attempt_{repair_index}_rejected.java.txt").write_text(repaired, encoding="utf-8")
                            result = {"status": "integrity_rejected", "output": str(integrity["errors"]), "xml_file": ""}
                            break
                    test_code = repaired
                    test_file = write_test_file(test_code, gen_dir, test_class)
                    result = run_generated_test(method, test_file, test_class,
                                                execution_dir_for(output_root, round_index, repair_index, args.passing_only), args, cp_cache)
                    if args.passing_only:
                        result["semantic_review_required"] = True
                    (gen_dir / f"attempt_{repair_index}.java.txt").write_text(test_code, encoding="utf-8")
                    write_json(gen_dir / f"attempt_{repair_index}.json", {"result": result, "retrieved_knowledge": repair_kg})

                if include_incremental_xml(result, args.passing_only):
                    if args.exact_exec_union:
                        probe_union_feedback.accept_incremental(output_root / "probe_accepted_xml", result, method["id"], round_index)
                    else:
                        dest_dir = combined_xml / f"round{round_index}" / method["id"]
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(result["xml_file"], dest_dir / "jacoco.xml")
                status = {
                    "round": round_index,
                    "id": method["id"],
                    "project_id": method["project_id"],
                    "fqcn": method["fqcn"],
                    "method": method["method"],
                    "status": result["status"],
                    "test_class": result.get("test_class", ""),
                    "xml_file": result.get("xml_file", ""),
                    "semantic_review_required": result.get("semantic_review_required", False),
                    "retrieval_sources": retrieval_log,
                    "ablation_flags": {
                        "coverage_gap_retrieval_enabled": not args.disable_coverage_gap_retrieval,
                        "failure_repair_retrieval_enabled": not args.disable_failure_repair_retrieval,
                        "static_guard_enabled": not args.disable_static_guard,
                    },
                }
            except Exception as exc:
                status = {
                    "round": round_index,
                    "id": method["id"],
                    "project_id": method.get("project_id", ""),
                    "fqcn": method.get("fqcn", ""),
                    "method": method.get("method", ""),
                    "status": "error",
                    "error": str(exc),
                    "test_class": test_class,
                    "xml_file": "",
                }
            write_json(status_file, status)
            round_rows.append(status)
            all_round_rows.append(status)

        write_table(round_rows, output_root / f"round{round_index}_summary", "coverage_feedback_round")
        if args.exact_exec_union:
            probe_union_feedback.evaluate_round(args, output_root, method_list, round_index)
        else:
            evaluate(method_list, combined_xml, output_root / f"coverage_round{round_index}", args.approach_name, args.timeout,
                     args.reference_xml_root)
        current_summary = summary_from_output(output_root / f"coverage_round{round_index}")
        previous_lines = int(previous_summary.get("focal_lines_covered", 0) or 0)
        current_lines = int(current_summary.get("focal_lines_covered", 0) or 0)
        previous_branches = int(previous_summary.get("focal_branches_covered", 0) or 0)
        current_branches = int(current_summary.get("focal_branches_covered", 0) or 0)
        write_json(
            output_root / f"round{round_index}_coverage_delta.json",
            {
                "round": round_index,
                "line_delta": current_lines - previous_lines,
                "branch_delta": current_branches - previous_branches,
                "previous": previous_summary,
                "current": current_summary,
            },
        )
        previous_summary = current_summary

    write_table(all_round_rows, output_root, "coverage_feedback_generation_summary")
    print(json.dumps(previous_summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
