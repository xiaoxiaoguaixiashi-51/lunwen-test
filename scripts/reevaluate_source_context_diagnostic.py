"""Re-evaluate saved F0/F1/F2 suites uniformly, without model requests or edits."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_stage_b_ours_full_feedback as feedback
from scripts import probe_union_feedback as probe
from scripts.build_kcf_coverage_reference import digest
from scripts.run_kcf_development_pilot import score, write
from src.core.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--projects-root', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path, required=True)
    args = parser.parse_args()
    saved, output = args.saved_root.resolve(), args.output_dir.resolve()
    methods_file = saved / 'methods.json'
    methods = json.loads(methods_file.read_text())
    old = json.loads((saved / 'execution_statuses.json').read_text())
    if len(old) != 6 or len(methods) != 2:
        raise ValueError('Require complete original two-target diagnostic')
    output.mkdir(parents=True, exist_ok=False)
    rows, results, source_hashes = [], {}, []
    options = SimpleNamespace(projects_root=args.projects_root, timeout=120,
        jacoco_agent='/root/tools/jacocoagent.jar', jacoco_cli='/root/tools/jacococli.jar',
        passing_only=True, strict_evaluation=True, evaluation_reference_root=args.reference_root)
    for arm in ('F0', 'F1', 'F2'):
        directory = output / arm
        accepted = directory / 'accepted_xml'
        accepted.mkdir(parents=True)
        entries = []
        for method in methods:
            previous = next(r for r in old if r['id'] == method['id'] and r['arm'] == arm)
            sources = list((saved / arm / 'sources' / method['id']).glob('*.java'))
            row = {'id': method['id'], 'arm': arm}
            if not sources and previous['status'] in {'generation_budget_blocked', 'generation_no_class'}:
                row.update(status=previous['status'], xml_file='')
            elif len(sources) == 1:
                original = sources[0]
                source = directory / 'source_copies' / method['id'] / original.name
                source.parent.mkdir(parents=True)
                shutil.copyfile(original, source)
                if digest(source) != digest(original):
                    raise ValueError('Saved source changed')
                source_hashes.append({'arm': arm, 'id': method['id'], 'original': str(original),
                                      'copy': str(source), 'sha256': digest(source)})
                name = Pipeline._extract_class_name(None, source.read_text(encoding='utf-8'))
                row.update(feedback.run_generated_test(method, source, name, directory / 'execution', options, {}))
                if row['status'] == 'ok':
                    xml = Path(row['xml_file'])
                    filename = method['id'] + '.xml'
                    shutil.copy2(xml, accepted / filename)
                    entries.append({'id': method['id'], 'status': 'ok', 'xml_name': filename,
                        'xml_sha256': digest(xml), 'semantic_review_required': False,
                        'origin': 'unchanged_saved_source_context_suite', **probe.execution_fields(xml)})
            else:
                raise ValueError('Ambiguous or missing saved generated source')
            rows.append({k: v for k, v in row.items() if k != 'output'})
            write(output / 'execution_statuses.json', rows)
        write(accepted / 'accepted_xml_index.json', entries)
        results[arm] = score(methods_file, accepted, [directory / 'execution'], args.reference_root,
                             args.projects_root, directory / 'score', arm)
    write(output / 'summary.json', {'kind': 'uniform_saved_source_context_reevaluation', 'api_calls': 0,
        'generated_sources_changed': False, 'source_hashes': source_hashes,
        'execution_statuses': rows, 'results': results, 'formal_run_ready': False,
        'supersedes_evaluation_only': str(saved),
        'code_revision': __import__('subprocess').check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()})
    print(json.dumps({'completed': True, 'api_calls': 0, 'results': results}))


if __name__ == '__main__':
    main()
