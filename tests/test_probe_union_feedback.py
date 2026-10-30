import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import probe_union_feedback as probe
from scripts.build_kcf_coverage_reference import digest
from scripts.merge_kcf_execution_coverage import class_tree_hash, resolve_executions
from scripts.run_stage_b_ours_full_feedback import read_detail
from scripts import run_stage_b_ours_full_feedback as runner


class ProbeRoundTest(unittest.TestCase):
    def test_exact_mode_requires_fixed_reference_and_passing_only(self):
        args = SimpleNamespace(exact_exec_union=False)
        probe.validate_exact_mode(args)
        args = SimpleNamespace(exact_exec_union=True, passing_only=False)
        with self.assertRaisesRegex(ValueError, "passing-only"):
            probe.validate_exact_mode(args)
        args = SimpleNamespace(exact_exec_union=True, passing_only=True,
                               exact_reference_root=None, seed_execution_roots=[])
        with self.assertRaisesRegex(ValueError, "reference root"):
            probe.validate_exact_mode(args)

    def test_explicit_provenance_and_mutation_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = root / "accepted"
            accepted.mkdir()
            executions = []
            for name in ("one", "two"):
                execution = root / "runs" / name
                (execution / "xml").mkdir(parents=True)
                (execution / "xml/jacoco.xml").write_text("<report/>")
                (execution / "jacoco.exec").write_bytes(b"probes")
                (execution / "junit.log").write_text("OK (1 test)")
                executions.append(execution)
            probe.write_index(accepted, [])
            result = {"status": "ok", "xml_file": str(executions[0] / "xml/jacoco.xml")}
            probe.accept_incremental(accepted, result, "t", 1)
            # Identical XML in two runs is safe only with this explicit hashed provenance.
            self.assertEqual(1, len(resolve_executions(accepted, {"t": {"project_id": "p"}}, [root / "runs"])))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                probe.accept_incremental(accepted, result, "t", 1)
            with self.assertRaisesRegex(ValueError, "accepted passing"):
                probe.accept_incremental(accepted, {**result, "semantic_review_required": True}, "t", 2)
            with self.assertRaisesRegex(ValueError, "accepted passing"):
                probe.accept_incremental(accepted, {**result, "status": "test_failed"}, "t", 2)
            (executions[0] / "jacoco.exec").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                resolve_executions(accepted, {"t": {"project_id": "p"}}, [root / "runs"])

    @unittest.skipUnless(os.environ.get("KCF_JACOCO_TOOLS"), "Real Java/JaCoCo required")
    def test_complementary_round_removes_gap_with_fixed_denominator(self):
        tools = Path(os.environ["KCF_JACOCO_TOOLS"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            classes = projects / "p/target/classes"
            classes.mkdir(parents=True)
            source = projects / "p/Choice.java"
            source.write_text("public class Choice {\n public static int choose(boolean b) { return b ? 1 : 2; }\n"
                              " public static void main(String[] a) { choose(Boolean.parseBoolean(a[0])); }\n}\n")
            def run(*args):
                return subprocess.run(list(args), capture_output=True, text=True, check=True).stdout
            run("javac", "-g", "-d", str(classes), str(source))
            ref = root / "reference"
            xml = ref / "xml/p/jacoco.xml"
            xml.parent.mkdir(parents=True)
            cli = tools / "jacococli.jar"
            prefix = ["java", "-jar", str(cli)]
            run(*prefix, "report", "--classfiles", str(classes), "--xml", str(xml))
            (ref / "reference_manifest.json").write_text(json.dumps({"jacoco_cli_sha256": digest(cli), "projects": [
                {"project_id": "p", "class_tree_sha256": class_tree_hash(classes), "xml_sha256": digest(xml)}]}))
            method = {"id": "t", "project_id": "p", "fqcn": "Choice", "class_name": "Choice", "method": "choose",
                      "target": str(source), "source_sha256": digest(source),
                      "method_owner": "Choice", "method_parameter_types": ["boolean"]}
            methods = root / "methods.json"
            methods.write_text(json.dumps([method]))
            output = root / "feedback"
            output.mkdir()
            seeds = root / "seed-executions"
            original = root / "accepted-seeds"
            original.mkdir()
            execution_xmls = []
            for choice, execution in (("true", seeds / "one"),
                                      ("false", output / "incremental_jacoco/round1/attempt0/t")):
                (execution / "xml").mkdir(parents=True)
                run("java", f"-javaagent:{tools / 'jacocoagent.jar'}=destfile={execution / 'jacoco.exec'},append=false",
                    "-cp", str(classes), "Choice", choice)
                run(*prefix, "report", str(execution / "jacoco.exec"), "--classfiles", str(classes),
                    "--xml", str(execution / "xml/jacoco.xml"))
                # Synthetic collector fixture, not a real JUnit generation experiment.
                (execution / "junit.log").write_text("OK (1 test)")
                execution_xmls.append(execution / "xml/jacoco.xml")
            (original / "seed.xml").write_bytes(execution_xmls[0].read_bytes())
            probe.write_index(original, [{"id": "t", "status": "ok", "semantic_review_required": False,
                                          "xml_name": "seed.xml", "xml_sha256": digest(original / "seed.xml"), "origin": "synthetic"}])
            args = SimpleNamespace(exact_exec_union=True, passing_only=True, exact_reference_root=str(ref),
                                   reference_xml_root=str(ref / "xml"), seed_execution_roots=[str(seeds)],
                                   projects_root=str(projects), jacoco_cli=str(cli), approach_name="KCF_UTG")
            probe.validate_exact_mode(args)
            actual_output = root / "actual-driver"
            argv = ["feedback", "--method-list", str(methods), "--raw-xml-root", str(original),
                    "--projects-root", str(projects), "--output-dir", str(actual_output),
                    "--reference-xml-root", str(ref / "xml"), "--exact-reference-root", str(ref),
                    "--seed-execution-roots", str(seeds), "--passing-only", "--exact-exec-union",
                    "--max-rounds", "0", "--approach-name", "KCF_UTG", "--jacoco-cli", str(cli)]
            with patch("sys.argv", argv), patch.object(runner, "load_config", return_value={}), patch.object(
                    runner, "LLMClient", side_effect=AssertionError("No client in offline round zero")):
                runner.main()
            actual = runner.summary_from_output(actual_output / "coverage_round0")
            self.assertEqual(1, actual["focal_branches_covered"])
            self.assertFalse((actual_output / "llm_calls.jsonl").exists())
            probe.prepare_seed_index(original, output / "probe_accepted_xml", {"t": method}, [seeds])
            first = probe.evaluate_round(args, output, methods, 0)[0]
            self.assertEqual(1, first["focal_branches_covered"])
            self.assertEqual(2, first["focal_branches_total"])
            self.assertEqual(1, len(read_detail(output / "coverage_round0/focal_method_coverage_detail.csv", "KCF_UTG")))
            probe.accept_incremental(output / "probe_accepted_xml", {"status": "ok", "xml_file": str(execution_xmls[1])}, "t", 1)
            second = probe.evaluate_round(args, output, methods, 1)[0]
            self.assertEqual(2, second["focal_branches_covered"])
            self.assertEqual(first["focal_branches_total"], second["focal_branches_total"])
            self.assertEqual(first["focal_lines_total"], second["focal_lines_total"])
            self.assertEqual([], read_detail(output / "coverage_round1/focal_method_coverage_detail.csv", "KCF_UTG"))
            self.assertEqual(2, len(json.loads((output / "probe_union_round1/execution_union_manifest.json").read_text())["executions"]))
            self.assertEqual(1, len(json.loads((output / "probe_union_round0/accepted_xml_index_snapshot.json").read_text())))
            self.assertEqual(2, len(json.loads((output / "probe_union_round1/accepted_xml_index_snapshot.json").read_text())))
