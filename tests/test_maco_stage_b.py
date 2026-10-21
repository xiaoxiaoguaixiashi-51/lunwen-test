import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.maco_stage_b import (
    ProjectSpec,
    buildability_check,
    collect_candidates,
    discover_classpath_entries,
    evosuite_command,
    load_projects,
    run_command,
    select_methods,
)


class MacoStageBTest(unittest.TestCase):
    def test_loads_project_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "projects.json"
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "project_id": "demo",
                            "name": "Demo",
                            "version": "1.0",
                            "java": 8,
                            "target_methods": 1,
                            "repo_url": "",
                            "refs": [],
                            "source_roots": ["src/main/java"],
                            "build_commands": [["mvn", "test-compile"]],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            projects = load_projects(manifest)

            self.assertEqual("demo", projects[0].project_id)
            self.assertEqual(1, projects[0].target_methods)

    def test_collects_and_selects_project_quota(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "demo" / "src" / "main" / "java" / "org" / "example"
            source_root.mkdir(parents=True)
            (source_root / "Service.java").write_text(
                """
package org.example;

public class Service {
  private final Helper helper = new Helper();

  public int complex(String value, int count) {
    if (value == null) {
      throw new IllegalArgumentException();
    }
    return helper.normalize(value).length() + Math.max(count, 0);
  }

  public int simple() {
    return 1;
  }
}

class Helper {
  String normalize(String value) { return value.trim(); }
}
""",
                encoding="utf-8",
            )
            project = ProjectSpec(
                project_id="demo",
                name="Demo",
                version="1.0",
                java=8,
                target_methods=1,
                repo_url="",
                refs=[],
                source_roots=["src/main/java"],
                build_commands=[],
            )

            candidates = collect_candidates([project], root)
            selected = select_methods([project], candidates, threshold=0.0)

            self.assertEqual(2, len(candidates))
            self.assertEqual(1, len(selected))
            self.assertEqual("demo", selected[0]["project_id"])
            self.assertIn("mdci", selected[0])

    def test_buildability_marks_missing_checkout(self):
        project = ProjectSpec(
            project_id="missing",
            name="Missing",
            version="1.0",
            java=8,
            target_methods=1,
            repo_url="",
            refs=[],
            source_roots=["src/main/java"],
            build_commands=[["mvn", "test-compile"]],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = buildability_check([project], Path(tmpdir) / "projects", Path(tmpdir) / "out", timeout=1)

            self.assertEqual("missing_checkout", rows[0]["status"])

    def test_run_command_records_timeout_output(self):
        status, return_code, output = run_command(
            [sys.executable, "-c", "import time; print('started'); time.sleep(2)"],
            Path.cwd(),
            timeout=1,
        )

        self.assertEqual("timeout", status)
        self.assertEqual(-1, return_code)
        self.assertIn("TIMEOUT", output)

    def test_evosuite_command_targets_class(self):
        command = evosuite_command(
            Path("/tools/evosuite.jar"),
            Path("/workspace/demo"),
            "org.example.Service",
            Path("/workspace/out"),
            search_budget=15,
        )

        self.assertIn("-class", command)
        self.assertIn("org.example.Service", command)
        self.assertIn("-Dsearch_budget=15", command)

    def test_discovers_common_classpath_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target" / "classes").mkdir(parents=True)
            (root / "build" / "classes" / "java" / "main").mkdir(parents=True)
            (root / "build" / "classes").mkdir(parents=True, exist_ok=True)
            (root / "build" / "core").mkdir(parents=True, exist_ok=True)

            entries = discover_classpath_entries(root)

            self.assertIn(root / "target" / "classes", entries)
            self.assertIn(root / "build" / "classes" / "java" / "main", entries)
            self.assertIn(root / "build" / "classes", entries)
            self.assertIn(root / "build" / "core", entries)

    def test_buildability_records_classpath_entries_after_successful_build_command(self):
        project = ProjectSpec(
            project_id="demo",
            name="Demo",
            version="1.0",
            java=8,
            target_methods=1,
            repo_url="",
            refs=[],
            source_roots=["src/main/java"],
            build_commands=[[sys.executable, "--version"]],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "projects" / "demo"
            (project_root / "target" / "classes").mkdir(parents=True)

            rows = buildability_check([project], root / "projects", root / "out", timeout=10)

            self.assertEqual("ok", rows[0]["status"])
            self.assertEqual(1, rows[0]["classpath_entry_count"])
            self.assertIn("target", rows[0]["classpath_entries"])

    def test_evosuite_command_uses_discovered_and_extra_classpath(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "build" / "classes" / "java" / "main").mkdir(parents=True)

            command = evosuite_command(
                Path("/tools/evosuite.jar"),
                root,
                "org.example.Service",
                root / "out",
                classpath_extra="/extra/dependency.jar",
            )

            project_cp = command[command.index("-projectCP") + 1]
            test_dir = next(part for part in command if part.startswith("-Dtest_dir=")).split("=", 1)[1]
            self.assertIn(str(root / "build" / "classes" / "java" / "main"), project_cp)
            self.assertIn("/extra/dependency.jar", project_cp)
            self.assertTrue(Path(test_dir).is_absolute())


if __name__ == "__main__":
    unittest.main()
