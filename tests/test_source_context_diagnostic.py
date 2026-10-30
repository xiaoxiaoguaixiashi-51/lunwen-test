import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.run_source_context_diagnostic import generate_stages, task_messages, MAX_ATTEMPTS, CheckedClient
from src.utils.request_budget import BudgetExceeded


class SourceContextDiagnosticTest(unittest.TestCase):
    def test_usage_is_checked_after_each_request_before_returning(self):
        class Client:
            def generate(self, *args):
                return 'response'
        with patch('scripts.run_source_context_diagnostic.check_costs', side_effect=RuntimeError('unknown usage')) as check:
            with self.assertRaisesRegex(RuntimeError, 'unknown usage'):
                CheckedClient(Client(), Path('run')).generate('system', 'user')
            check.assert_called_once_with(Path('run'), 18)

    def test_context_reaches_all_stages_without_path_replacement(self):
        calls = []
        class Client:
            def generate(self, system, user, **kwargs):
                calls.append((system, user))
                return '{}' if len(calls) < 3 else '```java\npublic class FooTest {}\n```'
        with tempfile.TemporaryDirectory() as directory:
            with patch('src.agents.generation_agent.GenerationAgent._prompts_for_source', return_value=('SYSTEM', 'JUnit 4')) as selector:
                code = generate_stages(Client(), 'EXACT_SELECTED_CONTEXT', {'target': '/real/project/Foo.java'},
                                       {'method_name': 'foo'}, [{'id': 'frozen'}], Path(directory))
        self.assertEqual(3, len(calls))
        self.assertTrue(all('EXACT_SELECTED_CONTEXT' in user for _, user in calls))
        self.assertIn('frozen', calls[1][1])
        selector.assert_called_once_with('/real/project/Foo.java')
        self.assertIn('class FooTest', code)
        self.assertEqual(18, MAX_ATTEMPTS)

    def test_budget_rejection_never_advances_to_plan_or_generation(self):
        class Client:
            def generate(self, *args, **kwargs):
                raise BudgetExceeded('local input rejection')
        with tempfile.TemporaryDirectory() as directory, patch('scripts.run_source_context_diagnostic.PlanAgent') as plan:
            with self.assertRaises(BudgetExceeded):
                generate_stages(Client(), 'context', {'target': 'unused'}, {}, [], Path(directory))
            plan.assert_not_called()

    def test_task_prompt_has_exact_ast_and_source(self):
        messages = task_messages('selected source', {'method_owner': 'a.Foo', 'method_parameter_types': ['int']})
        self.assertEqual(['system', 'user'], [m['role'] for m in messages])
        self.assertIn('selected source', messages[1]['content'])
        self.assertIn('a.Foo', messages[1]['content'])


if __name__ == '__main__':
    unittest.main()
