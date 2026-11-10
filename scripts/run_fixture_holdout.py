"""Two-target paired repair pilot with a setup-only execution arm."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from scripts import probe_union_feedback as probe
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts.build_kcf_coverage_reference import digest
from scripts.merge_kcf_execution_coverage import class_tree_hash
from scripts.minimal_source_context import context_parts
from scripts.run_kcf_development_pilot import check_costs, score, write
from scripts.run_source_context_diagnostic import CheckedClient
from src.core.llm_client import LLMClient, trace_target
from src.core.pipeline import Pipeline
from src.utils.llm_output import extract_fenced_block
from src.utils.request_budget import BudgetExceeded


MARKER = '// KCF_FOCAL'


def setup_prefix(code, focal):
    """Fail closed on layouts outside the pilot's one-test source contract."""
    if len(re.findall(r'(?m)^\s*@Test\s*$', code)) != 1 or code.count(MARKER) != 1:
        return None
    before, after = code.split(MARKER)
    call = r'\.\s*' + re.escape(focal) + r'\s*\('
    if re.search(call, before) or len(re.findall(call, after)) != 1:
        return None
    return before + '\n    }\n}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output-dir', 'tokenizer', 'private-config', 'projects-root', 'reference-root'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    spec = json.loads((repo / 'experiments/protocols/fixture_holdout_v1.json').read_text())
    protocol = json.loads((repo / 'experiments/protocols/kcf_rerun_v1.json').read_text())
    methods_file = repo / protocol['method_list']
    if digest(methods_file) != protocol['method_list_sha256'] or digest(args.tokenizer) != protocol['tokenizer_sha256']:
        raise ValueError('Frozen method list or tokenizer changed')
    configuration = yaml.safe_load(args.private_config.read_text())
    if any(configuration['llm'].get(k) != v for k, v in protocol['model'].items()):
        raise ValueError('Model configuration changed')
    methods = [m for m in json.loads(methods_file.read_text()) if m['project_id'] == 'jdom2'
               and m['class_name'] + '.' + m['method'] in spec['targets']]
    if len(methods) != len(spec['targets']):
        raise ValueError('Ambiguous target list')
    sources = {m['id']: context_parts(m)['mandatory'] for m in methods}
    reference = json.loads((args.reference_root / 'reference_manifest.json').read_text())
    jdom = next(p for p in reference['projects'] if p['project_id'] == 'jdom2')
    if (class_tree_hash(args.projects_root / 'jdom2/build/core') != jdom['class_tree_sha256']
            or digest(args.reference_root / 'xml/jdom2/jacoco.xml') != jdom['xml_sha256']
            or digest(Path('/root/tools/jacococli.jar')) != reference['jacoco_cli_sha256']):
        raise ValueError('Frozen execution environment changed')
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / 'spec.json', {**spec, 'frozen_protocol': protocol})
    write(root / 'methods.json', methods)
    options = SimpleNamespace(projects_root=args.projects_root, timeout=120, passing_only=True,
        jacoco_agent='/root/tools/jacocoagent.jar', jacoco_cli='/root/tools/jacococli.jar',
        strict_evaluation=True, evaluation_reference_root=args.reference_root,
        disable_static_guard=False, disable_failure_repair_retrieval=True, max_tokens=8192)

    def client(arm):
        directory = root / arm
        directory.mkdir(exist_ok=True)
        cfg = copy.deepcopy(configuration)
        cfg['request_budget'] = {**protocol['budget'], 'max_calls_per_target': 1,
            'tokenizer_json': str(args.tokenizer.resolve()), 'tokenizer_sha256': protocol['tokenizer_sha256'],
            'ledger_path': str(directory / 'budget.sqlite')}
        os.environ['KCF_LLM_TRACE_PATH'] = str(directory / 'llm_calls.jsonl')
        os.environ['KCF_EXPERIMENT_STAGE'] = arm
        return CheckedClient(LLMClient(cfg), root, spec['max_provider_attempts'])

    def evaluate(arm, method, code):
        name = Pipeline._extract_class_name(None, code)
        if not name:
            return {'status': 'generation_no_class', 'output': 'No Java class returned', 'xml_file': ''}
        path = feedback.write_test_file(code, root / arm / 'sources' / method['id'], name)
        start = time.monotonic()
        row = feedback.run_generated_test(method, path, name, root / arm / 'execution', options, {})
        return {**row, 'elapsed_seconds': time.monotonic() - start}

    def check_setup(arm, method, code):
        prefix = setup_prefix(code, method['method'])
        if prefix is None:
            return {'status': 'unavailable', 'elapsed_seconds': 0}
        result = evaluate(arm, method, prefix)
        return {'status': result['status'], 'elapsed_seconds': result.get('elapsed_seconds', 0),
                'output': result['output'][:2400]}

    all_rows = []
    accepted = {arm: [] for arm in spec['arms']}
    for index, method in enumerate(methods):
        target = method['id']
        source = sources[target]
        goal = spec['targets'][method['class_name'] + '.' + method['method']]
        instruction = ('Use one Java 8 JUnit 4 @Test method named testFocal. Put setup before a standalone '
                       '// KCF_FOCAL comment and the single direct focal invocation and assertions after it. '
                       'Keep the comment outside any try or block nested inside the test. Put this test last in the class. '
                       'Use at most 100 lines and preserve the stated test objective.')
        context = f'Objective: {goal}\n{instruction}\n\n{source}'
        with trace_target(target):
            raw = client('shared_seed').generate('Generate one complete Java test class. Output Java only.', context)
            seed = extract_fenced_block(raw, 'java')
            seed_result = evaluate('shared_seed', method, seed)
            arms = spec['arms'][index:] + spec['arms'][:index]
            for arm in arms:
                setup = check_setup('seed_setup', method, seed) if arm == 'setup_checked' else None
                final = seed_result
                final_setup = None
                if seed_result['status'] != 'ok':
                    diagnostics = seed_result['output']
                    if setup is not None:
                        diagnostics += '\nSetup-only execution (ends before focal invocation): ' + json.dumps(setup)
                    try:
                        code, _ = feedback.repair_test(client(arm), seed, method, diagnostics,
                            'initial_test_failure', [], options, source_context=context)
                        if arm == 'setup_checked':
                            final_setup = check_setup('repaired_setup', method, code)
                        final = evaluate(arm, method, code)
                    except BudgetExceeded:
                        final = {'status': 'budget_blocked', 'xml_file': ''}
                all_rows.append({'id': target, 'arm': arm, 'seed_status': seed_result['status'],
                    'seed_setup': setup, 'repaired_setup': final_setup,
                    **{k: v for k, v in final.items() if k != 'output'}})
                write(root / 'execution_statuses.json', all_rows)
                if final['status'] == 'ok':
                    xml = Path(final['xml_file'])
                    destination = root / arm / 'accepted_xml'
                    destination.mkdir(parents=True, exist_ok=True)
                    name = target + '.xml'
                    shutil.copy2(xml, destination / name)
                    accepted[arm].append({'id': target, 'status': 'ok', 'xml_name': name,
                        'xml_sha256': digest(xml), 'semantic_review_required': False,
                        'origin': 'passing_suite_pending_manual_intent_audit', **probe.execution_fields(xml)})
    scores = {}
    for arm, entries in accepted.items():
        folder = root / arm / 'accepted_xml'
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / 'accepted_xml_index.json', entries)
        scores[arm] = score(root / 'methods.json', folder, [root / arm / 'execution', root / 'shared_seed/execution'],
            args.reference_root, args.projects_root, root / arm / 'score', arm)
    write(root / 'summary.json', {'rows': all_rows, 'coverage': scores, 'cost': check_costs(root, spec['max_provider_attempts'])})


if __name__ == '__main__':
    main()
