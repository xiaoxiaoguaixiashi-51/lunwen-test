"""Offline two-target F3 signature baseline and saved-output prompt-size replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.minimal_source_context import build_context
from scripts.source_api_context import SourceIndex, build_api_context
from scripts.run_source_context_diagnostic import TARGETS, static_analysis, task_messages
from src.agents.plan_agent import PlanAgent
from src.agents.generation_agent import GenerationAgent


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


class Capture:
    def generate(self, system, user, **kwargs):
        self.messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        return '{}'


def replay_sizes(context, analysis, dependency, plan, knowledge, source_file, count):
    capture = Capture()
    PlanAgent(capture).generate_plan(dependency, context, retrieved_knowledge=knowledge)
    plan_tokens = count(capture.messages)
    GenerationAgent(capture, static_guard_enabled=True).generate(plan, context, dependency, source_file=source_file)
    return {'first_task': count(task_messages(context, analysis)),
            'plan_with_saved_F1_dependency': plan_tokens,
            'generation_with_saved_F1_plan': count(capture.messages)}


def audit(args):
    repo = Path(__file__).resolve().parents[1]
    protocol = json.loads((repo / 'experiments/protocols/kcf_rerun_v1.json').read_text())
    method_file = repo / protocol['method_list']
    if hashlib.sha256(method_file.read_bytes()).hexdigest() != protocol['method_list_sha256']:
        raise ValueError('Frozen method list changed')
    tokenizer_path = args.inputs_root / 'tokenizer.json'
    if hashlib.sha256(tokenizer_path.read_bytes()).hexdigest() != protocol['tokenizer_sha256']:
        raise ValueError('Frozen tokenizer changed')
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    def count(messages):
        return protocol['budget']['framing_reserve'] + sum(
            len(tokenizer.encode(m['content'], add_special_tokens=False).ids) for m in messages)
    manifest = json.loads((args.inputs_root / 'input_manifest.json').read_text())
    source_hashes = {path.replace('\\', '/'): sha for path, sha in manifest['source_files'].items()}
    if len(source_hashes) != len(manifest['source_files']):
        raise ValueError('Ambiguous normalized source paths')
    methods = json.loads(method_file.read_text())
    archive_path = repo / 'results/source_context_diagnostic_20261030/kcf_context_diagnostic_20261030.tgz'
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != '7cf9da34ad96db0f1248cc7b4449e64e065f943fb6e0856fd990973894e03d92':
        raise ValueError('Saved diagnostic archive changed')
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    ceiling = protocol['budget']['max_input_tokens_per_call']
    # Fixed 4000-token headroom before observing the resulting F3 lengths; unchanged call ceiling.
    preparation_ceiling = ceiling - 4000
    with tarfile.open(archive_path) as saved:
        prepared_before = json.load(saved.extractfile('kcf-context-live-v2-20261030/prepared_contexts.json'))
        for project, name in TARGETS:
            matches = [m for m in methods if m['project_id'] == project and m['method'] == name]
            if len(matches) != 1:
                raise ValueError('Ambiguous development target')
            frozen = matches[0]
            prefix = project + '/' + frozen['source_root_relative'] + '/'
            expected = {path[len(prefix):]: sha for path, sha in source_hashes.items() if path.startswith(prefix)}
            source_root = args.inputs_root / project / frozen['source_root_relative']
            index = SourceIndex(source_root, expected)
            method = {**frozen, 'target': str(args.inputs_root / project / frozen['target_relative'])}
            analysis = static_analysis(method)
            fits = lambda source: count(task_messages(source, analysis)) <= preparation_ceiling
            f3 = build_api_context(method, index, fits)
            simple = build_context(method, lambda source: count(task_messages(source, analysis)) <= ceiling)
            contexts = {'F1': simple['F1'], 'F2': simple['F2'], 'F3': f3['F3']}
            previous = next(p for p in prepared_before if p['method']['id'] == frozen['id'])
            path = 'kcf-context-live-v2-20261030/F1/sources/' + frozen['id'] + '/'
            dependency = json.load(saved.extractfile(path + 'dependency_analysis.json'))
            plan = json.load(saved.extractfile(path + 'test_plan.json'))
            replay, parsed_replay = {}, {}
            parsed_dependency = {key: value for key, value in dependency.items() if key != 'raw_llm_response'}
            for arm, context in contexts.items():
                replay[arm] = replay_sizes(context, analysis, dependency, plan, previous['knowledge'], frozen['target'], count)
                parsed_replay[arm] = replay_sizes(context, analysis, parsed_dependency, plan,
                    previous['knowledge'], frozen['target'], count)
            def stage_fits(context):
                values = replay_sizes(context, analysis, parsed_dependency, plan,
                    previous['knowledge'], frozen['target'], count)
                return max(values.values()) <= ceiling - 512
            budgeted = build_api_context(method, index, stage_fits)
            budgeted_replay = replay_sizes(budgeted['F3'], analysis, parsed_dependency, plan,
                previous['knowledge'], frozen['target'], count)
            write(root / (frozen['id'] + '.json'), {'method': frozen, 'local_target': method['target'],
                'F3': f3, 'prompt_size_replay': replay, 'source_index_sha256': expected,
                'parsed_analysis_only_prompt_replay': parsed_replay,
                'F3_stage_budgeted_after_original_audit': budgeted,
                'stage_budgeted_parsed_analysis_replay': budgeted_replay})
            rows.append({'id': frozen['id'], 'source_sha256_matches_frozen_target': True,
                'source_index_files': len(expected), 'indexed_types': len(index.types),
                'mandatory_fits_preparation_ceiling': f3['mandatory_fits'],
                'included_api_types': f3['included_api_types'], 'excluded_api_types': f3['excluded_api_types'],
                'unresolved_type_candidates': f3['unresolved_type_candidates'], 'prompt_size_replay': replay,
                'parsed_analysis_only_prompt_replay': parsed_replay,
                'stage_budgeted_parsed_analysis_replay': budgeted_replay,
                'stage_budgeted_mandatory_fits': budgeted['mandatory_fits'],
                'stage_budgeted_included_api_types': budgeted['included_api_types'],
                'stage_budgeted_excluded_api_types': budgeted['excluded_api_types'],
                'focal_sha256': f3['focal_sha256'],
                'context_sha256': hashlib.sha256(f3['F3'].encode()).hexdigest()})
    result = {'kind': 'offline_signature_context_baseline_not_generation_or_novelty_results', 'api_calls': 0,
        'method_list_sha256': protocol['method_list_sha256'], 'tokenizer_sha256': protocol['tokenizer_sha256'],
        'call_input_ceiling_unchanged': ceiling, 'first_task_preparation_ceiling': preparation_ceiling,
        'reserved_future_stage_headroom': 4000, 'source_inputs': manifest['downloads'], 'rows': rows,
        'local_source_archives': manifest.get('local_archives', []),
        'live_run_ready': False,
        'remaining_execution_checks': ['cloud source/class parity', 'fresh later-stage model outputs under the unchanged budget'],
        'runtime': {'python': sys.version, 'tokenizers': __import__('tokenizers').__version__},
        'additional_exploratory_engineering_check': {
            'timing': 'after_original_first_prompt_only_F3_audit_revealed_later_stage_overflow',
            'prompt_view': 'keep static_analysis and llm_analysis; omit raw_llm_response from downstream prompts only',
            'same_parsed_view_measured_for_F1_F2_F3': True,
            'stage_budgeted_context_selection': 'whole optional dependency API blocks fit saved-output replay at input ceiling minus 512',
            'raw_responses_retained_in_original_archive': True,
            'semantic_equivalence_or_future_fit_claimed': False},
        'source_provenance': 'frozen target file hashes match; direct dependency source hashes newly recorded; cloud class/source parity not yet checked',
        'limits': ['Two known development targets, no independent holdout.',
                   'Later-stage sizes replay saved F1 semantic analysis/plans, not new F3 outputs or guaranteed future fit.',
                   'Source headers omit behavioral preconditions; no factory correctness, full type resolution or novelty claim.',
                   'New contexts have not been integrated into production or sent to the provider.'],
        'implementation_sha256': {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
            for name in ['scripts/source_api_context.py', 'scripts/audit_source_api_context.py']}}
    write(root / 'summary.json', result)
    print(json.dumps({'targets': len(rows), 'api_calls': 0,
                      'prompt_sizes': {row['id']: row['prompt_size_replay'] for row in rows},
                      'stage_budgeted_replay': {row['id']: row['stage_budgeted_parsed_analysis_replay'] for row in rows}}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    with patch('socket.socket', side_effect=AssertionError('Network forbidden in offline audit')):
        audit(args)


if __name__ == '__main__':
    main()
