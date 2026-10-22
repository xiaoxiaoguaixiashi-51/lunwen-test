import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_kcf_project_archives import extract_source


class ArchiveExtractionTest(unittest.TestCase):
    def test_extracts_files_without_generated_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                entry = tarfile.TarInfo("repo-commit/src/A.java")
                entry.size = 10
                handle.addfile(entry, io.BytesIO(b"class A {}"))
            extract_source(archive, root / "out")
            self.assertEqual("class A {}", (root / "out/src/A.java").read_text())

    def test_rejects_traversal_before_extracting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                handle.addfile(tarfile.TarInfo("repo/../../escape"), io.BytesIO())
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                extract_source(archive, root / "out")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
