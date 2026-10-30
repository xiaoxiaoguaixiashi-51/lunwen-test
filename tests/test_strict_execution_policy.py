import json
import os
from pathlib import Path
import tempfile
import subprocess
import xml.etree.ElementTree as ET
from types import SimpleNamespace
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from scripts import strict_execution_policy as policy
from scripts import run_stage_b_rag_llm_coverage as rag
from scripts import run_stage_b_evosuite_coverage as evo
from scripts import run_stage_b_ours_full_feedback as kcf
from scripts.build_kcf_coverage_reference import digest
from scripts.merge_kcf_execution_coverage import class_tree_hash, resolve_executions


class StrictExecutionPolicyTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("KCF_JACOCO_TOOLS"), "Real Java/JUnit/JaCoCo required")
    def test_three_actual_evaluators_same_main_only_junit_fixture(self):
        tools = Path(os.environ["KCF_JACOCO_TOOLS"])
        keep = os.environ.get("KCF_STRICT_EVAL_SMOKE_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=False)
        with (nullcontext(keep) if keep else tempfile.TemporaryDirectory()) as tmp:
            root = Path(tmp)
            project = root / "projects/p"
            classes = project / "target/classes"
            classes.mkdir(parents=True)
            source = project / "T.java"
            source.write_text("package p; public class T { public static int work(boolean b) { return b ? 1 : 2; } }")
            subprocess.run(["javac", "-g", "-d", str(classes), str(source)], check=True, capture_output=True)
            (project / "target/test-classes/p").mkdir(parents=True)
            (project / "target/test-classes/p/Leak.class").write_bytes(b"not part of the report")
            ref = root / "reference"
            (ref / "xml/p").mkdir(parents=True)
            xml = ref / "xml/p/jacoco.xml"
            cli = tools / "jacococli.jar"
            subprocess.run(["java", "-jar", str(cli), "report", "--classfiles", str(classes), "--xml", str(xml)],
                           check=True, capture_output=True)
            (ref / "reference_manifest.json").write_text(json.dumps({"jacoco_cli_sha256": digest(cli), "projects": [
                {"project_id": "p", "class_tree_sha256": class_tree_hash(classes), "xml_sha256": digest(xml)}]}))
            counts = []
            evidence = []
            for module, declared_package in ((rag, True), (evo, True), (kcf, True), (kcf, False)):
                case = module.__name__ + ("_default_package" if not declared_package else "")
                generated = root / case / "generated"
                folder = generated / ("p/p.T" if module is evo else "t")
                folder.mkdir(parents=True)
                name = "T_ESTest" if module is evo else "TTest"
                test = folder / (name + ".java")
                test.write_text(("package p; " if declared_package else "")
                                + "import org.junit.Test; import static org.junit.Assert.*; public class " + name
                                + " { @Test public void branch() { System.out.close(); assertEquals(1, p.T.work(true)); } }")
                (folder / "status.json").write_text(json.dumps({"status": "completed", "success": True}))
                method = {"id": "t", "project_id": "p", "fqcn": "p.T", "method": "work", "package": "p"}
                args = SimpleNamespace(projects_root=str(root / "projects"), output_dir=str(root / case / "output"),
                                       strict_evaluation=True, evaluation_reference_root=str(ref), timeout=30,
                                       jacoco_agent=str(tools / "jacocoagent.jar"), jacoco_cli=str(cli),
                                       evosuite_jar=str(tools / "evosuite.jar"), rag_dir=str(generated), evosuite_dir=str(generated),
                                       isolate_execution=True)
                if module is kcf:
                    result = module.run_generated_test(method, test, name, Path(args.output_dir), args, {})
                else:
                    result = module.run_one({**method, "status": "ok"}, args, {})
                log = Path(result["xml_file"]).parent.parent / "junit.log"
                self.assertEqual("ok", result["status"], module.__name__ + ": " + log.read_text())
                tree = ET.parse(result["xml_file"])
                self.assertEqual({"p/T"}, {c.get("name") for c in tree.findall(".//class")})
                branch = tree.find(".//class/counter[@type='BRANCH']")
                counts.append((int(branch.get("covered")), int(branch.get("missed"))))
                execution = Path(result["xml_file"]).parent.parent
                self.assertEqual(1, json.loads((execution / "junit_result.json").read_text())["tests_run"])
                evidence.append({"runner": module.__name__, "status": result["status"],
                                 "covered_branches": counts[-1][0], "missed_branches": counts[-1][1],
                                 "reported_classes": [c.get("name") for c in tree.findall(".//class")],
                                 "xml_sha256": digest(Path(result["xml_file"])), "exec_sha256": digest(execution / "jacoco.exec"),
                                 "timings": [json.loads(line) for line in (execution / "execution_timings.jsonl").read_text().splitlines()]})
            self.assertEqual([(1, 1)] * 4, counts)
            if keep:
                (root / "summary.json").write_text(json.dumps({"kind": "handwritten_evaluator_fixture_not_baseline_quality",
                    "api_calls": 0, "main_class_tree_sha256": class_tree_hash(classes), "evaluators": evidence}, indent=2) + "\n")

    def test_independent_failure_header_cannot_be_overridden_by_raw_stdout(self):
        text = "KCF independent JUnit Result evidence: fixture\nTests run: 2, Failures: 1\nOK (99 tests)\n"
        self.assertEqual("test_failed", policy.junit_status("ok", text))

    def test_only_frozen_main_classes_and_ant_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "p"
            classes = project / "target/classes"
            classes.mkdir(parents=True)
            (classes / "T.class").write_bytes(b"main")
            (project / "target/test-classes").mkdir()
            (project / "target/test-classes/Leak.class").write_bytes(b"test")
            (project / "lib").mkdir()
            (project / "lib/dependency.jar").write_bytes(b"library")
            ref = root / "reference"
            (ref / "xml/p").mkdir(parents=True)
            xml = ref / "xml/p/jacoco.xml"
            xml.write_text("<report/>")
            cli, agent = root / "cli.jar", root / "agent.jar"
            cli.write_bytes(b"cli")
            agent.write_bytes(b"agent")
            (ref / "reference_manifest.json").write_text(json.dumps({"jacoco_cli_sha256": digest(cli), "projects": [
                {"project_id": "p", "class_tree_sha256": class_tree_hash(classes), "xml_sha256": digest(xml)}]}))
            output = root / "out"
            output.mkdir()
            args = SimpleNamespace(evaluation_reference_root=str(ref), jacoco_cli=str(cli), jacoco_agent=str(agent))
            compile_cp, report_cp = policy.classpaths(args, "p", project, output)
            self.assertEqual([str(classes.resolve())], report_cp)
            self.assertEqual(2, len(compile_cp))
            self.assertFalse(any("test-classes" in p for p in compile_cp))
            (classes / "T.class").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Main classes differ"):
                policy.classpaths(args, "p", project, output)

    def test_positive_junit_required_and_dependency_cache_is_lazy(self):
        self.assertEqual("ok", policy.junit_status("ok", "OK (2 tests)"))
        self.assertEqual("zero_or_unverified_tests", policy.junit_status("ok", "OK (0 tests)"))
        self.assertEqual("zero_or_unverified_tests", policy.junit_status("ok", ""))
        self.assertEqual("test_failed", policy.junit_status("failed", "OK (2 tests)"))
        with tempfile.TemporaryDirectory() as tmp:
            loader, cache = Mock(return_value="dependency"), {}
            for _ in range(2):
                self.assertEqual("dependency", policy.dependencies(cache, "p", loader, Path(tmp)))
            loader.assert_called_once()
            rows = [json.loads(line) for line in (Path(tmp) / "execution_timings.jsonl").read_text().splitlines()]
            self.assertEqual([False, True], [r["cache_hit"] for r in rows])

    def test_single_line_package_and_comments(self):
        self.assertEqual("p.q", policy.java_package("/* package fake; */ package p.q; public class T {}"))
        self.assertEqual("", policy.java_package("// package fake;\npublic class T {}"))

    def test_source_copy_and_evosuite_patch_never_change_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            text = "// separateClassLoader = true\nclass T {}"
            (source / "T.java").write_text(text)
            (source / "private.yaml").write_text("must-not-copy")
            policy.copy_java_sources(source, root / "copied", patch_evosuite=True)
            self.assertEqual(text, (source / "T.java").read_text())
            self.assertIn("separateClassLoader = false", (root / "copied/T.java").read_text())
            self.assertFalse((root / "copied/private.yaml").exists())
            with self.assertRaises(FileExistsError):
                policy.copy_java_sources(source, root / "copied")

    def test_class_execution_can_map_to_two_focal_methods_without_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution = root / "execution"
            (execution / "xml").mkdir(parents=True)
            xml = execution / "xml/jacoco.xml"
            xml.write_text("<report/>")
            (execution / "junit.log").write_text("OK (2 tests)")
            (execution / "jacoco.exec").write_bytes(b"probes")
            methods = [{"id": i, "project_id": "p", "fqcn": "p.T"} for i in ("one", "two")]
            policy.publish_accepted([{"project_id": "p", "fqcn": "p.T", "status": "ok", "xml_file": str(xml)}], methods, root, "evosuite")
            records = resolve_executions(root / "accepted_xml", {m["id"]: m for m in methods}, [execution])
            self.assertEqual(2, len(records))
            self.assertEqual(1, len({r["exec_file"] for r in records}))

    def test_three_runners_use_same_isolated_report_and_no_zero_test_success(self):
        for module in (rag, evo, kcf):
            with self.subTest(runner=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project = root / "projects/p"
                project.mkdir(parents=True)
                generated = root / "generated"
                method = {"id": "t", "project_id": "p", "fqcn": "p.T", "method": "work", "package": "p"}
                folder = generated / ("p/p.T" if module is evo else "t")
                folder.mkdir(parents=True)
                filename = "T_ESTest.java" if module is evo else "TTest.java"
                test = folder / filename
                test.write_text("package p;\npublic class " + test.stem + " {}")
                (folder / "status.json").write_text(json.dumps({"status": "completed", "success": True}))
                args = SimpleNamespace(projects_root=str(root / "projects"), rag_dir=str(generated), evosuite_dir=str(generated),
                                       output_dir=str(root / "output"), strict_evaluation=True, timeout=10,
                                       evosuite_jar="runtime.jar", jacoco_agent="agent.jar", jacoco_cli="cli.jar", isolate_execution=True)
                calls = []
                def run(command, cwd, timeout):
                    calls.append(command)
                    if command[0] == "java" and "-jar" not in command:
                        return "ok", 0, "OK (0 tests)"
                    if "--xml" in command:
                        Path(command[command.index("--xml") + 1]).write_text('<report><sourcefile><line nr="1"/></sourcefile></report>')
                    return "ok", 0, ""
                with patch.object(module, "run", side_effect=run), patch.object(module, "dependency_classpath", return_value=""), patch.object(
                        module, "junit_classpath", return_value=[]), patch.object(module, "discover_classpath_entries", return_value=["main", "test-classes"]), patch.object(
                        policy, "classpaths", return_value=(["frozen-main"], ["frozen-main"])):
                    if module is kcf:
                        result = module.run_generated_test(method, test, test.stem, root / "output", args, {})
                    elif module is evo:
                        result = module.run_one({**method, "status": "ok"}, args, {})
                    else:
                        result = module.run_one(method, args, {})
                    self.assertEqual("zero_or_unverified_tests", result["status"])
                    agent = next(x for command in calls for x in command if x.startswith("-javaagent:"))
                    self.assertIn("append=false", agent)
                    report = next(command for command in calls if "--xml" in command)
                    self.assertEqual(1, report.count("--classfiles"))
                    self.assertEqual("frozen-main", report[report.index("--classfiles") + 1])
                    self.assertNotIn("test-classes", " ".join(calls[0]))
                    with self.assertRaises(FileExistsError):
                        if module is kcf:
                            module.run_generated_test(method, test, test.stem, root / "output", args, {})
                        else:
                            module.run_one({**method, "status": "ok"}, args, {})
