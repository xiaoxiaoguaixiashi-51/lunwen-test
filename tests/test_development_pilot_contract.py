import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_kcf_development_pilot import check_costs, budget_rejected_without_source
from src.core.pipeline import Pipeline, PipelineResult


class DevelopmentPilotContractTest(unittest.TestCase):
    def test_frozen_pilot_request_bound_and_existing_rq(self):
        protocol = json.loads((Path(__file__).resolve().parents[1]/'experiments/protocols/kcf_rerun_v1.json').read_text())
        initial = 3 + protocol['initial_compile_attempts'] - 1
        per_method = initial + 1 + protocol['pilot']['feedback_rounds'] * (1 + protocol['feedback_repair_requests_per_round'])
        expected = len(protocol['pilot']['target_pairs']) * (4 * per_method + 1)
        self.assertEqual(66, expected)
        self.assertEqual(expected, protocol['pilot']['max_provider_attempts_all_arms'])
        self.assertEqual(['RQ1','RQ2'], protocol['research_questions'])
        self.assertEqual(5, len(protocol['formal_evosuite_seeds']))
        self.assertFalse(protocol['formal_run_ready'])

    def test_provider_error_and_global_bound_stop_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = [{'call_id': 'one', 'status': 'error', 'provider_call_attempted': True,
                       'sdk_max_retries': 0, 'usage': None, 'elapsed_seconds': 1}]
            (root/'llm_calls.jsonl').write_text(json.dumps(events[0])+'\n')
            with self.assertRaisesRegex(RuntimeError, 'unknown usage'):
                check_costs(root, 66)
            events[0].update(status='ok', usage={'prompt_tokens':1, 'completion_tokens':1, 'total_tokens':2})
            (root/'llm_calls.jsonl').write_text(json.dumps(events[0])+'\n')
            with self.assertRaisesRegex(RuntimeError, 'bound exceeded'):
                check_costs(root, 0)

    def test_kcf_preserves_actual_class_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline = Pipeline(llm_client=object(), compiler=object())
            result = PipelineResult('Foo.java', 'work', final_test='public final class FooSpec {}')
            pipeline._save_results(result, str(root))
            self.assertEqual(['FooSpec.java'], [path.name for path in root.glob('*.java')])

    def test_no_source_is_budget_failure_only_with_final_local_rejection_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'llm_calls.jsonl'
            event = {'target_id': 'm', 'status': 'budget_blocked', 'provider_call_attempted': False}
            path.write_text(json.dumps(event)+'\n')
            self.assertTrue(budget_rejected_without_source(root, 'm'))
            self.assertFalse(budget_rejected_without_source(root, 'another'))
            path.write_text(json.dumps(event)+'\n'+json.dumps({**event, 'status': 'ok', 'provider_call_attempted': True})+'\n')
            self.assertFalse(budget_rejected_without_source(root, 'm'))


if __name__ == '__main__':
    unittest.main()
