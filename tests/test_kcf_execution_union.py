import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.merge_kcf_execution_coverage import check_execution_ids, class_tree_hash, resolve_executions
from scripts.build_kcf_coverage_reference import digest
from scripts.analyze_focal_method_coverage import load_coverage_xmls


class ExecutionUnionTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("KCF_JACOCO_TOOLS"), "Optional real Java/JaCoCo toolchain test")
    def test_real_complementary_branches_need_probe_union(self):
        tools = Path(os.environ["KCF_JACOCO_TOOLS"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            classes = root / "classes"
            classes.mkdir()
            source = root / "Choice.java"
            source.write_text('public class Choice {\n public static int choose(boolean b) { return b ? 1 : 2; }\n'
                              ' public static void main(String[] args) { choose(Boolean.parseBoolean(args[0])); }\n}\n')
            def run(*args):
                return subprocess.run(list(args), check=True, capture_output=True, text=True).stdout
            run("javac", "-g", "-d", str(classes), str(source))
            single = []
            for choice in ("true", "false"):
                folder = root / choice
                folder.mkdir()
                data = folder / "jacoco.exec"
                run("java", f"-javaagent:{tools / 'jacocoagent.jar'}=destfile={data},append=false",
                    "-cp", str(classes), "Choice", choice)
                run("java", "-jar", str(tools / "jacococli.jar"), "report", str(data),
                    "--classfiles", str(classes), "--xml", str(folder / "jacoco.xml"))
                single.append(load_coverage_xmls(folder)["Choice"][2].branch_covered)
            merged = root / "merged"
            merged.mkdir()
            data = merged / "jacoco.exec"
            run("java", "-jar", str(tools / "jacococli.jar"), "merge", str(root / "true/jacoco.exec"),
                str(root / "false/jacoco.exec"), "--destfile", str(data))
            run("java", "-jar", str(tools / "jacococli.jar"), "report", str(data),
                "--classfiles", str(classes), "--xml", str(merged / "jacoco.xml"))
            exact = load_coverage_xmls(merged)["Choice"][2].branch_covered
            self.assertEqual([1, 1], single)
            self.assertEqual(2, exact)
            self.assertLess(max(single), exact)

    def test_different_class_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "Different executed class"):
            check_execution_ids("0123456789abcdef 1 of 2 p/T\n1123456789abcdef 2 of 2 p/T")
        self.assertEqual({"p/T": "0123456789abcdef"},
                         check_execution_ids("0123456789abcdef 1 of 2 p/T\n0123456789abcdef 2 of 2 p/T"))
        with self.assertRaises(ValueError):
            check_execution_ids("unrecognized output")

    def test_class_tree_changes_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "T.class").write_bytes(b"original")
            old = class_tree_hash(root)
            (root / "T.class").write_bytes(b"changed")
            self.assertNotEqual(old, class_tree_hash(root))

    def test_provenance_closed_passing_unambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = root / "accepted"
            execution = root / "runs/suite"
            accepted.mkdir()
            (execution / "xml").mkdir(parents=True)
            (execution / "xml/jacoco.xml").write_text("<report/>")
            (execution / "jacoco.exec").write_bytes(b"probes")
            log = execution / "junit.log"
            log.write_text("OK (2 tests)")
            (accepted / "t.xml").write_text("<report/>")
            entry = {"id": "t", "xml_name": "t.xml", "xml_sha256": digest(accepted / "t.xml"),
                     "status": "ok", "semantic_review_required": False, "origin": "reviewed"}
            index = accepted / "accepted_xml_index.json"
            index.write_text(json.dumps([entry]))
            methods = {"t": {"project_id": "p"}}
            self.assertEqual(1, len(resolve_executions(accepted, methods, [root / "runs"])))
            log.write_text("Tests run: 2, Failures: 1")
            with self.assertRaisesRegex(ValueError, "passing JUnit"):
                resolve_executions(accepted, methods, [root / "runs"])
            log.write_text("OK (2 tests)")
            index.write_text(json.dumps([{**entry, "semantic_review_required": True}]))
            with self.assertRaisesRegex(ValueError, "Unaccepted"):
                resolve_executions(accepted, methods, [root / "runs"])
            index.write_text(json.dumps([entry]))
            second = root / "runs/other/xml"
            second.mkdir(parents=True)
            (second / "jacoco.xml").write_text("<report/>")
            (second.parent / "jacoco.exec").write_bytes(b"other")
            (second.parent / "junit.log").write_text("OK (1 test)")
            with self.assertRaisesRegex(ValueError, "found 2"):
                resolve_executions(accepted, methods, [root / "runs"])


if __name__ == "__main__":
    unittest.main()
