import unittest
from pathlib import Path
from scripts.reevaluate_knowledge_diagnostic import absolute_output


class EvaluationPathTest(unittest.TestCase):
    def test_output_is_absolute_before_project_cwd_switch(self):
        path = absolute_output("experiments/runs/example")
        self.assertTrue(path.is_absolute())
        self.assertEqual(Path.cwd() / "experiments/runs/example", path)
