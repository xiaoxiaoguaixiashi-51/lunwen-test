"""Uniform zero-API re-evaluation of saved initial and incremental pilot source."""
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
from scripts.run_kcf_development_pilot import command, score, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--projects-root', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    saved, output = args.saved_root.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    methods_file = saved/'methods.json'
    methods = json.loads(methods_file.read_text())
    results, source_index, states = {}, [], {}
    for baseline, script, source_option in [('RAG','scripts/run_stage_b_rag_llm_coverage.py','--rag-dir'),
                                            ('EvoSuite','scripts/run_stage_b_evosuite_coverage.py','--evosuite-dir')]:
        directory = output/baseline
        directory.mkdir()
        source = saved/baseline/('initial' if baseline=='RAG' else 'generated')
        extra = [] if baseline=='RAG' else ['--evosuite-summary',saved/baseline/'evosuite_baseline_summary.csv']
        command([script, source_option, source, '--method-list', methods_file, '--projects-root',args.projects_root,
                 '--output-dir',directory/'execution', '--strict-evaluation','--evaluation-reference-root',args.reference_root,
                 '--timeout','120', *extra], repo, directory/'evaluation.log')
        results[baseline] = score(methods_file,directory/'execution/accepted_xml',[directory/'execution'],
                                 args.reference_root,args.projects_root,directory/'score',baseline)
        for path in source.rglob('*.java'):
            source_index.append({'source':str(path),'sha256':digest(path),'arm':baseline})
    for arm in ('Full','A1','A2','A3'):
        directory = output/arm
        accepted = directory/'accepted_xml'
        accepted.mkdir(parents=True)
        entries, rows = [], []
        options = SimpleNamespace(projects_root=args.projects_root, timeout=120, jacoco_agent='/root/tools/jacocoagent.jar',
            jacoco_cli='/root/tools/jacococli.jar', passing_only=True, strict_evaluation=True,
            evaluation_reference_root=args.reference_root)
        for method in methods:
            sources = list((saved/arm/'initial'/method['id']).glob('*.java'))
            candidates = [('initial',sources[0])] if len(sources)==1 else []
            incremental = saved/arm/'feedback/generated_tests/round1'/method['id']/'attempt_0.java.txt'
            if incremental.is_file():
                candidates.append(('incremental',incremental))
            if not candidates:
                rows.append({'id':method['id'],'phase':'initial','status':'saved_generation_missing_zero_coverage'})
            for phase, original in candidates:
                name = original.stem if phase=='initial' else feedback.class_name_for(method,1)
                source = directory/'source_copies'/phase/method['id']/(name+'.java')
                source.parent.mkdir(parents=True)
                shutil.copyfile(original,source)
                if digest(source)!=digest(original):
                    raise ValueError('Saved generated source changed')
                source_index.append({'source':str(original),'copy':str(source),'sha256':digest(source),'arm':arm})
                execution = directory/'execution'/phase
                execute = feedback.run_generated_test if phase=='initial' else feedback.run_initial_generated_test
                result = execute(method,source,name,execution,options,{})
                row = {'id':method['id'],'phase':phase,**{k:v for k,v in result.items() if k!='output'}}
                rows.append(row)
                if result['status']=='ok':
                    xml = Path(result['xml_file'])
                    filename = phase+'__'+method['id']+'.xml'
                    shutil.copy2(xml,accepted/filename)
                    entries.append({'id':method['id'],'status':'ok','xml_name':filename,'xml_sha256':digest(xml),
                        'semantic_review_required':False,'origin':'saved_unrepaired_'+phase+'_suite',**probe.execution_fields(xml)})
        write(accepted/'accepted_xml_index.json',entries)
        write(directory/'execution_statuses.json',rows)
        states[arm]=rows
        results[arm]=score(methods_file,accepted,[directory/'execution'],args.reference_root,args.projects_root,
                           directory/'score',arm)
    if {(r['focal_lines_total'],r['focal_branches_total']) for r in results.values()}!={(36,17)}:
        raise ValueError('Fixed denominator changed')
    write(output/'reevaluation_summary.json',{'kind':'saved_pilot_sources_uniform_independent_junit_result_zero_api',
        'new_api_calls':0,'results':results,'source_hashes':source_index,'execution_statuses':states,
        'repair_candidates_still_pending_excluded':True,'formal_run_ready':False})
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
