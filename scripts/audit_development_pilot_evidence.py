"""Audit saved live pilot evidence; never sends API requests or changes ledgers."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.summarize_request_costs import aggregate
from scripts.summarize_phase_costs import aggregate as phase_summary


def read(path):
    return json.loads(path.read_text())


def jsonlines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def audit(root):
    summary = read(root/'pilot_summary.json')
    if set(summary['results']) != {'Full','A1','A2','A3','RAG','EvoSuite'}:
        raise ValueError('Not all planned arms finished')
    costs, checks, phases, statuses, inputs = {}, {}, {}, {}, {}
    total_attempts = 0
    for arm in ('Full','A1','A2','A3','RAG'):
        directory = root/arm
        events = []
        for path in directory.rglob('llm_calls.jsonl'):
            events.extend(jsonlines(path))
            inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        cost = aggregate(events)
        costs[arm] = cost
        total_attempts += cost['totals']['provider_attempts']
        with sqlite3.connect((directory/'budget.sqlite').resolve().as_uri()+'?mode=ro', uri=True) as db:
            count, charged = db.execute('SELECT count(*),COALESCE(sum(charged),0) FROM calls').fetchone()
            states = dict(db.execute('SELECT status,count(*) FROM calls GROUP BY status'))
            if set(states)-{'settled'} or count != cost['totals']['provider_attempts'] or charged != cost['known_usage_totals']['total_tokens']:
                raise ValueError('Trace and ledger do not reconcile')
        checks[arm] = {'provider_attempts_match_ledger': True, 'usage_matches_charged_tokens': True, 'ledger_states': states}
        span_events = []
        for path in directory.rglob('phase_calls.jsonl'):
            span_events.extend(jsonlines(path))
        phases[arm] = phase_summary(span_events)
        statuses[arm] = {'local_budget_rejections': [
            {'target_id': event['target_id'], 'stage': event['stage'], 'provider_call_attempted': event['provider_call_attempted']}
            for event in events if event['status']=='budget_blocked']}
        if arm == 'RAG':
            continue
        stages = [read(directory/stage/'run_metadata.json') for stage in ('initial','seed_repair','feedback')]
        if len({entry['config_sha256'] for entry in stages}) != 1:
            raise ValueError('Cross-stage private config identity changed')
        ledger_paths = {entry['config_redacted']['request_budget']['ledger_path'] for entry in stages}
        if len(ledger_paths) != 1 or Path(next(iter(ledger_paths))).resolve() != (directory/'budget.sqlite').resolve():
            raise ValueError('Stages did not reference the same budget ledger')
        initial, seed, feedback = [entry['effective_settings'] for entry in stages]
        actual = {'initial_retrieval': initial['knowledge_retrieval_enabled'],
                  'initial_guard': initial['static_guard_enabled'],
                  'seed_retrieval': seed['failure_repair_retrieval_enabled'], 'seed_guard': seed['static_guard_enabled'],
                  'feedback_failure_retrieval': feedback['failure_repair_retrieval_enabled'],
                  'feedback_gap_retrieval': feedback['coverage_gap_retrieval_enabled'],
                  'feedback_guard': feedback['static_guard_enabled']}
        expected = {'initial_retrieval': arm!='A1', 'initial_guard': arm!='A3',
                    'seed_retrieval': arm!='A1', 'seed_guard': arm!='A3',
                    'feedback_failure_retrieval': arm!='A1', 'feedback_gap_retrieval': arm not in {'A1','A2'},
                    'feedback_guard': arm!='A3'}
        if actual != expected:
            raise ValueError('Effective ablation switches differ from protocol')
        checks[arm]['effective_switches'] = actual
        checks[arm]['same_config_and_ledger_all_stages'] = True
        statuses[arm]['initial'] = read(directory/'initial_execution/initial_execution.json')
        statuses[arm]['seed_repair'] = read(directory/'seed_repair/failure_repair_summary.json')
        statuses[arm]['feedback'] = read(directory/'feedback/coverage_feedback_generation_summary.json')
    denominator = {(row['focal_lines_total'], row['focal_branches_total']) for row in summary['results'].values()}
    if denominator != {(36,17)} or total_attempts>66:
        raise ValueError('Pilot denominator or request limit violated')
    return {'kind': 'two_development_targets_live_feasibility_audit_not_formal_results', 'results': summary['results'],
            'api_costs_by_arm': costs, 'provider_attempts': total_attempts, 'checks_by_arm': checks,
            'phase_timings_by_arm': phases, 'status_evidence': statuses, 'trace_sha256': inputs,
            'fixed_denominator_all_arms': True, 'formal_run_ready': False,
            'private_original_unchanged': summary['private_original_unchanged'],
            'notes': ['Development targets and single repeat do not establish effectiveness or novelty',
                      'Identical ceilings are not equal realized compute', 'Repaired suites pending semantic review remain excluded']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run_root.resolve())
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'provider_attempts': result['provider_attempts'], 'all_effective_switch_checks_passed': True}))


if __name__ == '__main__':
    main()
