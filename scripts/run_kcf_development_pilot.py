"""Bounded two-target live workflow check, not a formal effectiveness experiment.

Private configs are cloned into a fresh private directory. Existing configs stay
unchanged. Real initial generation, strict execution, seed repair and one feedback
round use the same per-arm ledger. No automatic semantic approval of repairs.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import time
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts import strict_execution_policy as strict
from scripts.maco_stage_b import evosuite_command, evosuite_row, write_table, unique_focal_classes
from scripts.merge_kcf_execution_coverage import merge_accepted_coverage
from scripts.preflight_kcf_run_plan import template, audit_plan
from scripts.summarize_request_costs import aggregate as api_summary
from src.core.batch_runner import run_batch
from src.core.llm_client import trace_target
from src.core.pipeline import Pipeline
from src.utils.experiment_metadata import write_run_metadata
from src.utils.phase_trace import phase


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def command(argv, root, log):
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run([sys.executable, *map(str, argv)], cwd=root, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError("Child stage failed; inspect saved stage log")


def check_costs(run, maximum):
    events = []
    for path in run.rglob("llm_calls.jsonl"):
        events.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    summary = api_summary(events)
    if summary["totals"].get("provider_attempts", 0) > maximum:
        raise RuntimeError("Pilot request bound exceeded")
    if any(event["status"] == "error" or (event.get("budget_settlement") or {}).get("status") in {"unknown", "overrun"} for event in events):
        raise RuntimeError("Provider failure, unknown usage or overrun; no automatic retry")
    write(run / "api_costs.json", summary)
    return summary


def score(methods_file, accepted, roots, reference, projects, output, approach):
    return merge_accepted_coverage(SimpleNamespace(method_list=methods_file, accepted_xml_root=accepted,
        execution_roots=roots, reference_root=reference, projects_root=projects, jacoco_cli=Path('/root/tools/jacococli.jar'),
        java='java', output_dir=output, approach_name=approach, evaluation_dir=output / 'coverage'))[0]


def budget_rejected_without_source(initial, method_id):
    trace = initial / 'llm_calls.jsonl'
    if not trace.is_file():
        return False
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    target_events = [event for event in events if event.get('target_id') == method_id]
    return bool(target_events and target_events[-1].get('status') == 'budget_blocked'
                and target_events[-1].get('provider_call_attempted') is False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-config", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--resume-after-initial", choices=['Full','A1','A2','A3'], help="Continue a stopped pilot using its saved initial artifacts and unchanged ledgers")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    protocol_file = repo / 'experiments/protocols/kcf_rerun_v1.json'
    protocol = json.loads(protocol_file.read_text())
    root = args.output_dir.resolve()
    if args.resume_after_initial:
        if not (root/'pilot_stopped.json').is_file() or (root/'pilot_summary.json').exists():
            raise ValueError('Only a stopped unfinished pilot can resume')
        if json.loads((root/'frozen_protocol.json').read_text()) != protocol:
            raise ValueError('Protocol changed; do not resume under a different budget')
    else:
        root.mkdir(parents=True, exist_ok=False)
    private = repo / 'config/private' / root.name
    if not args.resume_after_initial:
        private.mkdir(parents=True, exist_ok=False)
    original = args.private_config.read_bytes()
    config = yaml.safe_load(original)
    if any(config['llm'].get(key) != value for key, value in protocol['model'].items()):
        raise ValueError('Existing model settings differ from frozen protocol; do not silently switch')
    tokenizer = args.tokenizer.resolve()
    if hashlib.sha256(tokenizer.read_bytes()).hexdigest() != protocol['tokenizer_sha256']:
        raise ValueError('Tokenizer changed')
    source = repo / protocol['method_list']
    if hashlib.sha256(source.read_bytes()).hexdigest() != protocol['method_list_sha256']:
        raise ValueError('Frozen formal methods changed')
    knowledge = repo / protocol['knowledge']
    if hashlib.sha256(knowledge.read_bytes()).hexdigest() != protocol['knowledge_sha256']:
        raise ValueError('Frozen knowledge changed')
    all_methods = json.loads(source.read_text())
    methods = []
    for project, name in protocol['pilot']['target_pairs']:
        matches = [m for m in all_methods if m['project_id'] == project and m['method'] == name]
        if len(matches) != 1:
            raise ValueError('Pilot target ambiguous')
        methods.extend(matches)
    methods_file = root / 'methods.json'
    if args.resume_after_initial:
        if json.loads(methods_file.read_text()) != methods:
            raise ValueError('Pilot targets changed')
    else:
        write(methods_file, methods)
    strict.frozen_methods(methods_file)
    plan = template(root)
    if not args.resume_after_initial:
        write(root / 'frozen_protocol.json', protocol)
    for arm in ('Full', 'A1', 'A2', 'A3', 'RAG'):
        cfg = json.loads(json.dumps(config))
        cfg['llm'].update(protocol['model'])
        cfg['pipeline'] = {'max_fix_iterations': protocol['initial_compile_attempts'], 'feedback_enabled': True}
        cfg['retrieval'] = {'enabled': arm != 'A1', 'knowledge_path': str(knowledge), 'max_examples': 3}
        cfg['static_guard'] = {'enabled': arm != 'A3'}
        cfg['request_budget'] = {**protocol['budget'], 'tokenizer_json': str(tokenizer),
            'tokenizer_sha256': protocol['tokenizer_sha256'], 'ledger_path': str(root / arm / 'budget.sqlite')}
        path = private / (arm + '.yaml')
        if args.resume_after_initial:
            if yaml.safe_load(path.read_text()) != cfg:
                raise ValueError('Private stage config changed; preserve original ledger policy')
        else:
            path.write_text(yaml.safe_dump(cfg))
            path.chmod(0o600)
        for job in plan['jobs']:
            if job['arm'] == arm:
                job['config'] = str(path)
    if args.resume_after_initial:
        if not json.loads((root/'preflight.json').read_text())['configuration_checks_passed']:
            raise ValueError('Original preflight did not pass')
        check_costs(root, 66)
        with (root/'resume_after_initial.json').open('x') as handle:
            json.dump({'arm': args.resume_after_initial, 'new_initial_requests': 0,
                       'reason': 'handle_local_budget_rejection_as_zero_generation_not_missing_infrastructure'}, handle)
    else:
        preflight = audit_plan(plan)
        write(root / 'plan.json', plan)
        write(root / 'preflight.json', preflight)
        if not preflight['configuration_checks_passed']:
            raise ValueError('Static preflight failed before any provider request')
    results = json.loads((root/'partial_results.json').read_text()) if args.resume_after_initial else {}
    try:
        # Independent one-shot RAG first; it also checks the existing provider configuration.
        arm = root / 'RAG'
        if not args.resume_after_initial:
            arm.mkdir()
            command(['-m', 'src.core.rag_llm_baseline_runner', '--methods', methods_file, '--output', arm/'initial',
                 '--config', private/'RAG.yaml', '--no-resume'], repo, arm/'generation.log')
            check_costs(root, 66)
            command(['scripts/run_stage_b_rag_llm_coverage.py', '--method-list', methods_file, '--rag-dir', arm/'initial',
                 '--projects-root', args.projects_root, '--output-dir', arm/'execution', '--strict-evaluation',
                 '--evaluation-reference-root', args.reference_root, '--timeout', '120'], repo, arm/'evaluation.log')
            results['RAG'] = score(methods_file, arm/'execution/accepted_xml', [arm/'execution'], args.reference_root,
                               args.projects_root, arm/'score', 'RAG')
            write(root/'partial_results.json', results)
        variants = ['Full', 'A1', 'A2', 'A3']
        if args.resume_after_initial:
            variants = variants[variants.index(args.resume_after_initial):]
        for variant in variants:
            arm = root / variant
            cfg_path = private / (variant + '.yaml')
            cfg = yaml.safe_load(cfg_path.read_text())
            os.environ['KCF_LLM_TRACE_PATH'] = str(arm/'initial/llm_calls.jsonl')
            os.environ['KCF_PHASE_TRACE_PATH'] = str(arm/'initial/phase_calls.jsonl')
            os.environ['KCF_EXPERIMENT_STAGE'] = 'initial_generation'
            if variant != args.resume_after_initial:
                write_run_metadata(arm/'initial', stage='initial_generation', method_list=methods_file,
                    config_path=cfg_path, config=cfg, knowledge_path=knowledge,
                    settings={'pilot': True, 'knowledge_retrieval_enabled': variant != 'A1', 'static_guard_enabled': variant != 'A3'})
                initial_summaries = []
                for method in methods:
                    initial_summaries.append(run_batch([method], str(arm/'initial'), cfg, resume=False))
                    check_costs(root, 66)
                write(arm/'initial/pilot_batch_summaries.json', initial_summaries)
            rows = []
            execution = arm/'initial_execution'
            options = SimpleNamespace(projects_root=args.projects_root, timeout=120, jacoco_agent='/root/tools/jacocoagent.jar',
                jacoco_cli='/root/tools/jacococli.jar', passing_only=True, strict_evaluation=True,
                evaluation_reference_root=args.reference_root)
            for method in methods:
                files = list((arm/'initial'/method['id']).glob('*.java'))
                if len(files) != 1:
                    if not files and budget_rejected_without_source(arm/'initial', method['id']):
                        rows.append({'id': method['id'], 'project_id': method['project_id'], 'fqcn': method['fqcn'],
                                     'status': 'generation_budget_blocked', 'xml_file': ''})
                        continue
                    raise RuntimeError('Initial generation did not produce exactly one saved Java artifact')
                name = Pipeline._extract_class_name(None, files[0].read_text())
                with trace_target(method['id']):
                    row = feedback.run_generated_test(method, files[0], name, execution, options, {})
                output = execution/method['project_id']/feedback.safe_name(f"{method['id']}-{method['fqcn']}")
                rows.append({**row, 'id': method['id'], 'project_id': method['project_id'], 'fqcn': method['fqcn'],
                             'source_dir': str(files[0].parent), 'output_dir': str(output)})
            write_table(rows, execution, 'initial_execution')
            if any(row['status'] not in {'ok', 'compile_failed', 'test_failed', 'generation_budget_blocked'} for row in rows):
                raise RuntimeError('Non-test infrastructure status; stop before repair')
            executable_ids = {row['id'] for row in rows if row['status'] != 'generation_budget_blocked'}
            seed_methods = [method for method in methods if method['id'] in executable_ids]
            seed_methods_file = arm/'seed_methods.json'
            write(seed_methods_file, seed_methods)
            write_table([row for row in rows if row['id'] in executable_ids], execution, 'repairable_execution')
            flags = ['--disable-static-guard'] if variant == 'A3' else []
            if variant == 'A1':
                flags += ['--disable-failure-repair-retrieval']
            command(['scripts/run_kcf_seed_failure_repair.py', '--method-list', seed_methods_file,
                '--coverage-summary', execution/'repairable_execution.csv', '--output-dir', arm/'seed_repair',
                '--projects-root', args.projects_root, '--config', cfg_path, '--knowledge-path', knowledge,
                '--evaluation-reference-root', args.reference_root, '--stop-on-provider-error', '--timeout', '120', *flags], repo, arm/'seed_repair.log')
            check_costs(root, 66)
            if variant in ('A1', 'A2'):
                flags += ['--disable-coverage-gap-retrieval']
            # Parent process environment points to initial traces; child must own fresh traces.
            os.environ.pop('KCF_LLM_TRACE_PATH', None)
            os.environ.pop('KCF_PHASE_TRACE_PATH', None)
            os.environ.pop('KCF_EXPERIMENT_STAGE', None)
            command(['scripts/run_kcf_utg_feedback.py', '--method-list', methods_file,
                '--raw-xml-root', arm/'seed_repair/accepted_xml', '--projects-root', args.projects_root,
                '--output-dir', arm/'feedback', '--config', cfg_path, '--knowledge-path', knowledge,
                '--max-rounds', '1', '--repair-iterations', '1', '--passing-only', '--exact-reference-root', args.reference_root,
                '--reference-xml-root', args.reference_root/'xml', '--seed-execution-roots', execution, arm/'seed_repair',
                '--stop-on-provider-error', '--timeout', '120', *flags], repo, arm/'feedback.log')
            check_costs(root, 66)
            final = arm/'feedback/coverage_round1/focal_method_coverage_summary.json'
            if not final.exists():
                final = arm/'feedback/coverage_round0/focal_method_coverage_summary.json'
            results[variant] = json.loads(final.read_text())[0]
            write(root/'partial_results.json', results)
        # Genuine EvoSuite generation, with a fixed pilot seed and class-level accounting.
        arm = root/'EvoSuite'
        arm.mkdir()
        generated = arm/'generated'
        rows = []
        for method in unique_focal_classes(methods):
            project = args.projects_root/method['project_id']
            output = generated/method['project_id']/method['fqcn']
            cmd = evosuite_command(Path('/root/tools/evosuite.jar'), project, method['fqcn'], output,
                search_budget=30, classpath_entries=[project/('build/core' if method['project_id']=='jdom2' else 'target/classes')])
            cmd += ['-seed', '31000']
            log = arm/(method['project_id']+'.log')
            os.environ['KCF_PHASE_TRACE_PATH'] = str(arm/'phase_calls.jsonl')
            os.environ['KCF_EXPERIMENT_STAGE'] = 'evosuite_generation'
            with phase('evosuite_class_generation', target_id=method['project_id']+'::'+method['fqcn']):
                status, code, text = feedback.run(cmd, project, 300)
            log.write_text(text)
            rows.append(evosuite_row(method, status, cmd, code, log))
        write_table(rows, arm, 'evosuite_baseline_summary')
        command(['scripts/run_stage_b_evosuite_coverage.py', '--evosuite-summary', arm/'evosuite_baseline_summary.csv',
            '--evosuite-dir', generated, '--projects-root', args.projects_root, '--output-dir', arm/'execution',
            '--strict-evaluation', '--evaluation-reference-root', args.reference_root, '--method-list', methods_file,
            '--timeout', '120'], repo, arm/'evaluation.log')
        results['EvoSuite'] = score(methods_file, arm/'execution/accepted_xml', [arm/'execution'], args.reference_root,
                                   args.projects_root, arm/'score', 'EvoSuite')
        summary = {'kind': protocol['pilot']['kind'], 'results': results, 'api_costs': check_costs(root, 66),
                   'private_original_unchanged': args.private_config.read_bytes() == original,
                   'formal_run_ready': False, 'semantic_review_pending_not_auto_approved': True}
        write(root/'pilot_summary.json', summary)
    except BaseException as exc:
        write(root/'pilot_stopped.json', {'error_type': type(exc).__name__, 'automatic_retry': False,
              'private_original_unchanged': args.private_config.read_bytes() == original})
        raise


if __name__ == '__main__':
    main()
