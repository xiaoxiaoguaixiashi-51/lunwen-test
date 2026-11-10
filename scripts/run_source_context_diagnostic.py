"""Bounded development-only F0/F1/F2 comparison; dry preparation unless --execute.

Three model stages, one generated suite, no repair/feedback, no formal RQ change.
Retrieval is frozen from full-source static analysis for each target across arms.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts import probe_union_feedback as probe
from scripts.build_kcf_coverage_reference import digest
from scripts.minimal_source_context import build_context
from scripts.run_kcf_development_pilot import check_costs, score, write
from scripts.merge_kcf_execution_coverage import class_tree_hash
from src.agents import task_agent
from src.agents.plan_agent import PlanAgent
from src.agents.generation_agent import GenerationAgent
from src.core.llm_client import LLMClient, trace_target
from src.core.pipeline import Pipeline
from src.retrieval.dependency_knowledge import retrieve_dependency_knowledge
from src.utils.java_parser import extract_dependencies
from src.utils.request_budget import BudgetExceeded


TARGETS = [('commons-cli', 'processArgs'), ('jdom2', 'getNamespacesInScope')]
ARMS = ('F0', 'F1', 'F2')
MAX_ATTEMPTS = len(TARGETS) * len(ARMS) * 3


class CheckedClient:
    """Settle/check every individual request before allowing the next stage."""
    def __init__(self, client, root, max_attempts=MAX_ATTEMPTS):
        self.client, self.root = client, root
        self.max_attempts = max_attempts

    def generate(self, *args, **kwargs):
        try:
            return self.client.generate(*args, **kwargs)
        finally:
            check_costs(self.root, self.max_attempts)


def static_analysis(method):
    selector = {key: method[key] for key in ('method_owner', 'method_parameter_types')}
    result = extract_dependencies(method['target'], method['method'], **selector).to_dict()
    return {**result, **selector}


def task_messages(context, analysis):
    return [{'role': 'system', 'content': task_agent.SYSTEM_PROMPT},
            {'role': 'user', 'content': task_agent.USER_PROMPT_TEMPLATE.format(
                source_code=context, ast_analysis=json.dumps(analysis, indent=2, ensure_ascii=False))}]


def generate_stages(client, context, method, analysis, knowledge, destination, *, parsed_only=False):
    """Same context in all stages; original path only selects project constraints."""
    messages = task_messages(context, analysis)
    raw = client.generate(messages[0]['content'], messages[1]['content'])
    dependency = {'static_analysis': analysis,
                  'llm_analysis': task_agent.TaskAgent._parse_llm_response(None, raw),
                  'raw_llm_response': raw}
    write(destination / 'dependency_analysis.json', dependency)
    if parsed_only:
        del dependency['raw_llm_response']
    plan = PlanAgent(client).generate_plan(dependency, context, retrieved_knowledge=knowledge)
    write(destination / 'test_plan.json', plan)
    return GenerationAgent(client, static_guard_enabled=True).generate(
        plan, context, dependency, source_file=method['target'])


def prepare(repo, tokenizer_path):
    protocol = json.loads((repo / 'experiments/protocols/kcf_rerun_v1.json').read_text())
    methods_file = repo / protocol['method_list']
    knowledge_file = repo / protocol['knowledge']
    for path, expected in [(methods_file, protocol['method_list_sha256']),
                           (knowledge_file, protocol['knowledge_sha256']),
                           (tokenizer_path, protocol['tokenizer_sha256'])]:
        if digest(path) != expected:
            raise ValueError('Frozen input changed: ' + path.name)
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    def count(messages):
        return protocol['budget']['framing_reserve'] + sum(
            len(tokenizer.encode(m['content'], add_special_tokens=False).ids) for m in messages)
    all_methods = json.loads(methods_file.read_text())
    prepared = []
    for project, name in TARGETS:
        matches = [m for m in all_methods if m['project_id'] == project and m['method'] == name]
        if len(matches) != 1:
            raise ValueError('Development target ambiguous')
        method = matches[0]
        analysis = static_analysis(method)
        context = build_context(method, lambda source: count(task_messages(source, analysis)) <=
                                protocol['budget']['max_input_tokens_per_call'])
        context['F0'] = Path(method['target']).read_text(encoding='utf-8')
        # Freeze retrieval from static-only full-source input: prompt context is the treatment.
        knowledge = retrieve_dependency_knowledge({'static_analysis': analysis, 'llm_analysis': {}},
            context['F0'], method['method'], knowledge_path=knowledge_file, max_examples=3)
        prepared.append({'method': method, 'analysis': analysis, 'contexts': context,
                         'knowledge': knowledge,
                         'first_input_estimates': {a: count(task_messages(context[a], analysis)) for a in ARMS}})
    return protocol, prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tokenizer', type=Path, required=True)
    parser.add_argument('--private-config', type=Path)
    parser.add_argument('--projects-root', type=Path)
    parser.add_argument('--reference-root', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--signature-audit', type=Path, help='Use the frozen offline F3 contexts and compare against F1')
    parser.add_argument('--fixture-pilot', type=Path, help='Replay the saved Element F3 plan for a paired generation-only comparison')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    protocol, prepared = prepare(repo, args.tokenizer.resolve())
    arms = ('F1', 'F3') if args.signature_audit else ARMS
    replay = None
    if args.signature_audit:
        from scripts.source_api_context import SourceIndex
        for target in prepared:
            method = target['method']
            evidence = json.loads((args.signature_audit / (method['id'] + '.json')).read_text(encoding='utf-8'))
            context = evidence['F3_stage_budgeted_after_original_audit']
            if evidence['method'] != method or not context['mandatory_fits'] or context['focal_sha256'] != target['contexts']['focal_sha256']:
                raise ValueError('Signature audit differs from the frozen target')
            SourceIndex(Path(method['target']).parents[len(Path(method['target_relative']).parts) - 1] / method['source_root_relative'],
                        evidence['source_index_sha256'])
            target['contexts']['F3'] = context['F3']
            target['signature_audit_sha256'] = digest(args.signature_audit / (method['id'] + '.json'))
    if args.fixture_pilot:
        if not args.signature_audit:
            parser.error('--fixture-pilot requires --signature-audit')
        prepared = [target for target in prepared if target['method']['project_id'] == 'jdom2']
        target, = prepared
        dependency_file = args.fixture_pilot / 'dependency_analysis.json'
        plan_file = args.fixture_pilot / 'test_plan.json'
        if (digest(dependency_file), digest(plan_file)) != (
            '183fe606226b28881ac14130ec3124d79eec599fe93aef7520956e542a29a835',
            '0d11625f204dbd6e33a956e92b86b81a5b7ed736a2c1d01ad52e5fa7e282ef60',
        ):
            raise ValueError('Saved Element F3 analysis or plan changed')
        dependency = json.loads(dependency_file.read_text())
        del dependency['raw_llm_response']
        replay = (json.loads(plan_file.read_text()), dependency)
        java = Path(target['method']['target']).parent
        excerpts = []
        for name, ranges in [('JDOMConstants', [(98, 98), (100, 100)]),
                             ('Namespace', [(98, 99), (112, 115), (201, 205), (221, 226)]),
                             ('Element', [(397, 400)]), ('AttributeList', [(195, 198)]),
                             ('Verifier', [(610, 619), (651, 657), (688, 707)])]:
            lines = (java / (name + '.java')).read_text(encoding='utf-8').splitlines()
            excerpts.extend(f'{name}.java:{start}-{end}\n' + '\n'.join(
                line.strip() for line in lines[start-1:end] if line.strip() and not line.lstrip().startswith('//'))
                for start, end in ranges)
        base = target['contexts']['F3'] + (
            '\nCheck fixture setup using the evidence below and the parent merge in the focal body above. '
            'If a planned scenario is impossible through the public API, replace it with a legal scenario that exercises the focal method. '
            'Derive expectations for the new scenario from the focal behavior. Preserve feasible original scenarios.\n')
        target['contexts']['source'] = base + '\n\n'.join(excerpts)
        target['contexts']['rules'] = base + (
            'The namespace factory reserves xml for http://www.w3.org/XML/1998/namespace and preloads that pair as Namespace.XML_NAMESPACE. '
            'It rejects either side of the pair being rebound. On the same Element, adding a declaration or a prefixed attribute checks the element namespace, declarations and attributes. '
            'An equal prefix with a different URI is a collision. An unprefixed attribute bypasses this namespace collision check. '
            'Checks are local to the element. In the focal method, inherited namespaces fill only prefixes absent locally, so a descendant can shadow an ancestor.')
        arms = ('source', 'rules')
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(args.tokenizer.resolve()))
        class Capture:
            def generate(self, system, user, **kwargs):
                self.size = protocol['budget']['framing_reserve'] + sum(
                    len(tokenizer.encode(message, add_special_tokens=False).ids) for message in (system, user))
                return ''
        estimates = {}
        for arm in arms:
            capture = Capture()
            GenerationAgent(capture, static_guard_enabled=True).generate(
                replay[0], target['contexts'][arm], replay[1], source_file=target['method']['target'])
            estimates[arm] = capture.size
        if max(estimates.values()) > protocol['budget']['max_input_tokens_per_call']:
            raise ValueError(f'Paired generation prompts exceed the common input budget: {estimates}')
        target['replayed_generation_estimates'] = estimates
    calls_per_job = 1 if replay else 3
    max_attempts = len(prepared) * len(arms) * calls_per_job
    root = args.output_dir.resolve()
    if args.execute and not all((args.private_config, args.projects_root, args.reference_root)):
        parser.error('Execution requires private config, projects and frozen reference')
    root.mkdir(parents=True, exist_ok=False)
    methods_file = root / 'methods.json'
    write(methods_file, [p['method'] for p in prepared])
    write(root / 'prepared_contexts.json', prepared)
    write(root / 'diagnostic_spec.json', {
        'kind': 'development_context_comparison_not_formal_full_or_ablation',
        'code_revision': __import__('subprocess').check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        'implementation_sha256': digest(Path(__file__)),
        'frozen_protocol': protocol, 'arms': arms,
        'target_pairs': [(p['method']['project_id'], p['method']['method']) for p in prepared],
        'parsed_only_in_both_arms': bool(args.signature_audit),
        'max_provider_attempts': max_attempts, 'max_calls_per_target_per_arm': calls_per_job,
        'replayed_generation_inputs': replay,
        'max_reserved_tokens_all_arms': max_attempts * (12000 + 8192),
        'replications': 1, 'repair_requests': 0, 'feedback_rounds': 0,
        'static_guard_enabled': True, 'retrieval': 'identical static-only full-source selection per target',
        'source_context': 'same selected context in Task, Plan and Generation; AST always from full source',
        'limits': ['Known development targets, not independent holdout or formal effectiveness.',
                   'F0 may block before generation; blocked targets retained with zero coverage.',
                   'Different context changes available information; no completeness or novelty claim.'],
        'execute': args.execute})
    if not args.execute:
        print(json.dumps({'prepared_targets': len(prepared), 'api_calls': 0, 'execution_started': False}))
        return
    import yaml
    config = yaml.safe_load(args.private_config.read_text())
    if any(config['llm'].get(k) != v for k, v in protocol['model'].items()):
        raise ValueError('Private model settings differ from frozen protocol')
    reference = json.loads((args.reference_root / 'reference_manifest.json').read_text())
    if digest(Path('/root/tools/jacococli.jar')) != reference['jacoco_cli_sha256']:
        raise ValueError('Frozen JaCoCo CLI changed')
    for project in {p['method']['project_id'] for p in prepared}:
        record = next(r for r in reference['projects'] if r['project_id'] == project)
        classes = args.projects_root / project / ('build/core' if project == 'jdom2' else 'target/classes')
        if class_tree_hash(classes) != record['class_tree_sha256'] or digest(
                args.reference_root / 'xml' / project / 'jacoco.xml') != record['xml_sha256']:
            raise ValueError('Project/reference changed before API calls')
    results, statuses = {}, []
    try:
        # Rotate deterministic order by target to reduce a fixed arm/time ordering.
        jobs = [(p, arms[i % len(arms):] + arms[:i % len(arms)]) for i, p in enumerate(prepared)]
        for prepared_target, job_arms in jobs:
            method = prepared_target['method']
            for arm in job_arms:
                directory = root / arm
                target = directory / 'sources' / method['id']
                target.mkdir(parents=True)
                cfg = json.loads(json.dumps(config))
                cfg['request_budget'] = {**protocol['budget'], 'max_calls_per_target': calls_per_job,
                    'tokenizer_json': str(args.tokenizer.resolve()), 'tokenizer_sha256': protocol['tokenizer_sha256'],
                    'ledger_path': str(directory / 'budget.sqlite')}
                os.environ['KCF_LLM_TRACE_PATH'] = str(directory / 'llm_calls.jsonl')
                os.environ['KCF_EXPERIMENT_STAGE'] = 'source_context_development'
                row = {'id': method['id'], 'arm': arm}
                try:
                    with trace_target(method['id']):
                        client = CheckedClient(LLMClient(cfg), root, max_attempts)
                        context = prepared_target['contexts'][arm]
                        if replay:
                            plan, dependency = replay
                            code = GenerationAgent(client, static_guard_enabled=True).generate(plan, context, dependency, source_file=method['target'])
                        else:
                            code = generate_stages(client, context, method, prepared_target['analysis'],
                                prepared_target['knowledge'], target, parsed_only=bool(args.signature_audit))
                    name = Pipeline._extract_class_name(None, code)
                    if not name:
                        (target / 'unparsed_response.java.txt').write_text(code, encoding='utf-8')
                        row.update(status='generation_no_class', xml_file='')
                    else:
                        source = target / (name + '.java')
                        source.write_text(code, encoding='utf-8')
                        options = SimpleNamespace(projects_root=args.projects_root, timeout=120,
                            jacoco_agent='/root/tools/jacocoagent.jar', jacoco_cli='/root/tools/jacococli.jar',
                            passing_only=True, strict_evaluation=True, evaluation_reference_root=args.reference_root)
                        row.update(feedback.run_generated_test(method, source, name,
                                   directory / 'execution', options, {}))
                        if row['status'] not in {'ok', 'compile_failed', 'test_failed', 'zero_or_unverified_tests'}:
                            raise RuntimeError('Infrastructure/timeout status; do not continue')
                except BudgetExceeded:
                    row.update(status='generation_budget_blocked', xml_file='')
                finally:
                    check_costs(root, max_attempts)
                statuses.append({k: v for k, v in row.items() if k != 'output'})
                write(root / 'execution_statuses.json', statuses)
        for arm in arms:
            directory = root / arm
            accepted = directory / 'accepted_xml'
            accepted.mkdir()
            entries = []
            for row in statuses:
                if row['arm'] == arm and row['status'] == 'ok':
                    xml = Path(row['xml_file'])
                    name = row['id'] + '.xml'
                    shutil.copy2(xml, accepted / name)
                    entries.append({'id': row['id'], 'status': 'ok', 'xml_name': name, 'xml_sha256': digest(xml),
                        'semantic_review_required': False, 'origin': 'unrepaired_initial_source_context',
                        **probe.execution_fields(xml)})
            write(accepted / 'accepted_xml_index.json', entries)
            results[arm] = score(methods_file, accepted, [directory / 'execution'], args.reference_root,
                                 args.projects_root, directory / 'score', arm)
        write(root / 'summary.json', {'kind': 'single_development_context_comparison_not_formal',
            'results': results, 'execution_statuses': statuses, 'api_costs': check_costs(root, max_attempts),
            'formal_run_ready': False})
        print(json.dumps({'completed': True, 'jobs': len(statuses), 'results': results}))
    except Exception as error:
        write(root / 'diagnostic_stopped.json', {'error_type': type(error).__name__,
              'completed_jobs': len(statuses), 'automatic_retry': False})
        raise


if __name__ == '__main__':
    main()
