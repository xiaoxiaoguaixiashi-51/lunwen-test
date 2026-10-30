from pathlib import Path
import tempfile
import unittest
from src.core.rag_llm_baseline_runner import RagLlmBaselineRunner, extract_public_class_name


class RagFilenameTest(unittest.TestCase):
    def test_actual_public_name_not_artificial_test_suffix(self):
        for name in ("FooSpec", "FooTests", "FooTest"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                code = "package p; public final class " + name + " {}"
                self.assertEqual(name, extract_public_class_name(code))
                runner = RagLlmBaselineRunner(llm_client=object())
                runner._save_results(root / "Foo.java", "work", [], code, str(root))
                self.assertEqual(code, (root / (name + ".java")).read_text())
                self.assertEqual([name + ".java"], [p.name for p in root.glob("*.java")])

    def test_comment_class_name_does_not_override_real_declaration(self):
        self.assertEqual("Real", extract_public_class_name("/* public class Fake {} */ public final class Real {}"))
