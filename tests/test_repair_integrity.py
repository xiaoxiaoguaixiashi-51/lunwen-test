import tempfile
import unittest
from pathlib import Path

from src.utils.repair_integrity import check_repair_integrity
from src.utils.dependency_declarations import declaration_context, grounded_context


class RepairIntegrityTest(unittest.TestCase):
    original = 'public class T { @org.junit.Test public void a() { org.junit.Assert.assertEquals(1, 2); } }'

    def test_oracle_change_requires_review_even_when_structure_is_preserved(self):
        result = check_repair_integrity(self.original, self.original.replace("1, 2", "2, 2"))
        self.assertTrue(result["ok"])
        self.assertTrue(result["semantic_review_required"])

    def test_deletion_assertion_removal_disabling_and_skipping_are_rejected(self):
        for code in (
            'public class T {}',
            'public class T { @org.junit.Test public void a() {} }',
            self.original.replace('@org.junit.Test', '@org.junit.Ignore @org.junit.Test'),
            self.original.replace('org.junit.Assert.assertEquals(1, 2);', 'org.junit.Assume.assumeTrue(false);'),
            self.original.replace('org.junit.Assert.assertEquals(1, 2);', 'org.junit.Assert.assertTrue(true);'),
            self.original.replace('org.junit.Assert.assertEquals(1, 2);', 'return;'),
        ):
            self.assertFalse(check_repair_integrity(self.original, code)["ok"])

    def test_constructor_and_class_interface_headers_come_from_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "p").mkdir()
            dependency = root / "p/Dep.java"
            dependency.write_text('package p;\npublic class Dep {\n public Dep(int n) {}\n public int value() { return 1; }\n}', encoding="utf-8")
            target = root / "T.java"
            target.write_text('import p.Dep; class T {}', encoding="utf-8")
            records = declaration_context(target, [root])
            self.assertEqual("p.Dep", records[0]["fqcn"])
            self.assertIn("public class Dep", records[0]["declarations"])
            self.assertIn("public Dep(int n)", records[0]["declarations"])
            self.assertEqual(64, len(records[0]["sha256"]))
            method = {"target": str(target), "source_root": str(root), "project_id": "p"}
            unguarded = grounded_context(method, root, False)
            self.assertEqual([], unguarded["declarations"])
            self.assertNotIn("Actual dependency declarations", unguarded["context"])
            self.assertIn("import p.Dep", unguarded["context"])
