"""Common isolated evaluation rules; never adds generation/repair to a baseline."""
import json
from pathlib import Path
import shutil
import time
import os
import javalang

from scripts.build_kcf_coverage_reference import digest
from scripts.merge_kcf_execution_coverage import class_tree_hash
from scripts.summarize_kcf_pilot import junit_counts


def enabled(args):
    return bool(getattr(args, "strict_evaluation", False))


def timing(root, stage, started, **fields):
    event = {"stage": stage, "elapsed_seconds": time.monotonic() - started, **fields}
    with (root / "execution_timings.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def classpaths(args, project_id, project_root, output):
    started = time.monotonic()
    reference = Path(args.evaluation_reference_root).resolve()
    manifest = json.loads((reference / "reference_manifest.json").read_text(encoding="utf-8"))
    record = next(row for row in manifest["projects"] if row["project_id"] == project_id)
    classes = (project_root / ("build/core" if project_id == "jdom2" else "target/classes")).resolve()
    if class_tree_hash(classes) != record["class_tree_sha256"]:
        raise ValueError("Main classes differ from fixed reference")
    if digest(reference / "xml" / project_id / "jacoco.xml") != record["xml_sha256"]:
        raise ValueError("Reference XML changed")
    if digest(Path(args.jacoco_cli)) != manifest["jacoco_cli_sha256"]:
        raise ValueError("JaCoCo CLI differs from fixed reference")
    libraries = sorted((project_root / "lib").glob("*.jar"))
    policy = {"main_classes": str(classes), "class_tree_sha256": record["class_tree_sha256"],
              "reference_manifest_sha256": digest(reference / "reference_manifest.json"),
              "agent_sha256": digest(Path(args.jacoco_agent)), "append": False,
              "project_test_classes_in_classpath": False,
              "local_library_sha256": {str(p): digest(p) for p in libraries}}
    (output / "execution_policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    timing(output, "policy_validation", started)
    return [str(classes)] + [str(p.resolve()) for p in libraries], [str(classes)]


def dependencies(cache, project, loader, output):
    started = time.monotonic()
    hit = project in cache
    if not hit:
        cache[project] = loader()
    timing(output, "dependency_resolution", started, cache_hit=hit)
    return cache[project]


def execute(run, command, cwd, timeout, output, stage):
    started = time.monotonic()
    try:
        result = junit_execute(run, command, cwd, timeout, output) if stage == "junit" else run(command, cwd, timeout)
        timing(output, stage, started, status=result[0], return_code=result[1])
        return result
    except Exception:
        timing(output, stage, started, status="exception")
        raise


def junit_execute(run, command, cwd, timeout, output):
    """Save raw process output separately; derive canonical counts from JUnit Result."""
    marker = command.index("org.junit.runner.JUnitCore")
    cp_index = command.index("-cp") + 1
    classpath = command[cp_index]
    harness = output / "harness"
    harness.mkdir(exist_ok=False)
    source = Path(__file__).resolve().parent / "java/KcfJUnitEvidenceRunner.java"
    copied = harness / source.name
    shutil.copy2(source, copied)
    compile_result = run(["javac", "-source", "1.8", "-target", "1.8", "-cp", classpath,
                          "-d", str(harness), str(copied)], cwd, timeout)
    (output / "harness.compile.log").write_text(compile_result[2], encoding="utf-8")
    if compile_result[0] != "ok":
        return "harness_compile_failed", compile_result[1], "Independent JUnit harness compilation failed"
    evidence = output / "junit_result.json"
    invocation = list(command[:marker]) + ["KcfJUnitEvidenceRunner", str(evidence), *command[marker + 1:]]
    invocation[cp_index] = str(harness) + os.pathsep + classpath
    result = run(invocation, cwd, timeout)
    (output / "junit.process.log").write_text(result[2], encoding="utf-8")
    (output / "junit_harness_policy.json").write_text(json.dumps({"source_sha256": digest(source),
        "class_sha256": digest(harness / "KcfJUnitEvidenceRunner.class") if (harness / "KcfJUnitEvidenceRunner.class").is_file() else None,
        "process_status": result[0], "process_return_code": result[1]}) + "\n", encoding="utf-8")
    try:
        record = json.loads(evidence.read_text(encoding="utf-8"))
        if record.get("schema") != 1 or any(type(record[key]) is not int or record[key] < 0
                for key in ("tests_run", "failures", "ignored", "assumption_failures")):
            raise ValueError("Invalid JUnit evidence")
        count, failures = record["tests_run"], record["failures"]
        if count <= record["assumption_failures"]:
            return result[0], result[1], "No verified non-assumption tests\n"
        # The original console log is preserved. This summary comes from the
        # independent Result file, not a guessed count or a rewritten test.
        text = "KCF independent JUnit Result evidence: " + digest(evidence) + "\n"
        text += f"OK ({count} tests)\n" if failures == 0 else f"Tests run: {count}, Failures: {failures}\n"
        failure_log = Path(str(evidence) + ".failures.log")
        text += (failure_log.read_text(encoding="utf-8") if failure_log.is_file() else "") + result[2]
        return result[0], result[1], text
    except (OSError, ValueError, TypeError, KeyError):
        return result[0], result[1], "No verified independent JUnit Result file\n"


def junit_status(status, text):
    if status != "ok":
        return "test_" + status
    counts = junit_counts(text)
    if not isinstance(counts["tests_run"], int) or counts["tests_run"] <= 0:
        return "zero_or_unverified_tests"
    return "ok" if counts["failures"] == 0 else "test_failed"


def java_package(text):
    """Read the package token sequence, including legal single-line Java files."""
    tokens = iter(javalang.tokenizer.tokenize(text))
    for token in tokens:
        if token.value == "package":
            parts = []
            for part in tokens:
                if part.value == ";":
                    return "".join(parts)
                parts.append(part.value)
            raise ValueError("Unterminated package declaration")
    return ""


def copy_java_sources(source, destination, patch_evosuite=False):
    started = time.monotonic()
    destination.mkdir(parents=True, exist_ok=False)
    root = source.resolve()
    for path in sorted(source.rglob("*.java")):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Generated source link escapes input directory")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if patch_evosuite:
            text = path.read_text(encoding="utf-8").replace("separateClassLoader = true", "separateClassLoader = false")
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(path, target)
    timing(destination.parent, "source_copy", started, evosuite_classloader_patch=patch_evosuite)


def frozen_methods(path):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if len({m["id"] for m in items}) != len(items):
        raise ValueError("Duplicate frozen method IDs")
    for item in items:
        if digest(Path(item["target"])) != item["source_sha256"]:
            raise ValueError("Frozen source changed")
    return items


def publish_accepted(rows, methods, output, baseline):
    """One entry per focal target; EvoSuite class executions are not repeated."""
    accepted = output / "accepted_xml"
    accepted.mkdir(parents=True, exist_ok=False)
    entries = []
    mapping = {(r["project_id"], r["fqcn"]): r for r in rows} if baseline == "evosuite" else {r["id"]: r for r in rows}
    for method in methods:
        key = (method["project_id"], method["fqcn"]) if baseline == "evosuite" else method["id"]
        row = mapping.get(key)
        if not row or row["status"] != "ok":
            continue
        xml = Path(row["xml_file"]).resolve()
        execution = xml.parent.parent
        if junit_status("ok", (execution / "junit.log").read_text(encoding="utf-8")) != "ok":
            raise ValueError("Non-passing baseline suite cannot be accepted")
        name = method["id"] + ".xml"
        if Path(name).name != name:
            raise ValueError("Invalid focal method ID")
        shutil.copy2(xml, accepted / name)
        entries.append({"id": method["id"], "status": "ok", "xml_name": name, "xml_sha256": digest(xml),
                        "semantic_review_required": False, "origin": baseline + "_passing_unrepaired_suite",
                        "execution_xml": str(xml), "execution_exec_sha256": digest(execution / "jacoco.exec"),
                        "execution_junit_sha256": digest(execution / "junit.log")})
    (accepted / "accepted_xml_index.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
