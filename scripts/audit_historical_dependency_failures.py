"""Inventory a historical A3 archive without counting harness failures as dependency bugs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tarfile


def inventory(path):
    base = 'ablation_a3_wo_staticguard_raw_jacoco_v1_20260705'
    records = []
    with tarfile.open(path) as archive:
        members = {member.name: member for member in archive if member.isfile()}
        summary_member = base+'/ours_jacoco_summary.json'
        rows = json.load(archive.extractfile(summary_member))
        if len(rows)!=41 or len({row['id'] for row in rows})!=41:
            raise ValueError('Historical summary does not contain 41 unique target identities')
        for row in rows:
            directory = base+'/'+row['project_id']+'/'+row['output_dir'].rsplit('/',1)[-1]
            sources = []
            for name in sorted(members):
                if name.startswith(directory+'/src/') and name.endswith('.java'):
                    content = archive.extractfile(name).read()
                    sources.append({'member':name,'sha256':hashlib.sha256(content).hexdigest(),
                                    'junit_jupiter_import':b'org.junit.jupiter' in content,
                                    'mockito_import':b'org.mockito' in content})
            status = row['status']
            log_member = directory+('/compile.log' if status=='compile_failed' else '/junit.log')
            log_bytes = archive.extractfile(log_member).read() if log_member in members else None
            text = log_bytes.decode('utf-8',errors='replace') if log_bytes is not None else ''
            if status=='ok':
                category='historical_reported_pass_not_revalidated'
            elif status=='missing_generated_tests':
                category='missing_generated_tests'
            elif status=='compile_failed':
                category='compile_failure'
            elif 'No runnable methods' in text:
                category='junit_no_runnable_methods'
            elif 'InvalidTestClassError' in text:
                category='junit_invalid_test_class'
            elif status=='test_failed' and log_bytes is not None:
                category='runtime_failure_for_manual_review'
            else:
                category='unresolved_evidence'
            signals=[]
            for label,pattern in [('missing_junit_jupiter',r'package org\.junit\.jupiter[^\n]*does not exist'),
                                   ('missing_mockito',r'package org\.mockito[^\n]*does not exist'),
                                   ('missing_symbol',r'error: cannot find symbol'),
                                   ('type_mismatch',r'error: incompatible types'),
                                   ('unsupported_operation',r'UnsupportedOperationException'),
                                   ('namespace_collision',r'namespace prefix[^\n]*collides'),
                                   ('assertion_or_comparison_failure',r'AssertionError|ComparisonFailure')]:
                if re.search(pattern,text):
                    signals.append(label)
            excerpts = [line.strip() for line in text.splitlines() if re.search(
                r'^\d+\)|error:|Exception:|AssertionError|ComparisonFailure|not public|No runnable methods',line)]
            records.append({'id':row['id'],'project_id':row['project_id'],'fqcn':row['fqcn'],'method':row['method'],
                'historical_status':status,'evidence_category':category,'signals_not_causal_labels':signals,
                'source_files':sources,'log_member':log_member if log_bytes is not None else None,
                'log_sha256':hashlib.sha256(log_bytes).hexdigest() if log_bytes is not None else None,
                'selected_log_lines':excerpts[:12], 'retrieval_attribution':'unavailable_in_this_run',
                'current_full_reproduction_established':False})
    return {'kind':'historical_a3_evidence_inventory_not_new_effectiveness_results',
        'archive_filename':path.name,'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'summary_member':summary_member,'api_calls':0,'unique_target_methods':41,
        'project_count':len({row['project_id'] for row in records}),
        'category_counts':dict(Counter(row['evidence_category'] for row in records)),
        'targets_with_saved_source':sum(bool(row['source_files']) for row in records),
        'cases':records,
        'limits':['A3 disables project constraints; not representative of current Full error frequency',
                  'Historical statuses and source identities are preserved, not re-labelled as new KCF results',
                  'Suite coverage cannot establish whether a particular failing test reached the focal method',
                  'Log signals are evidence locations, not automatic oracle or dependency-cause adjudication']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=inventory(args.archive)
    with args.output.open('x',encoding='utf-8') as handle:
        handle.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'targets':result['unique_target_methods'],'categories':result['category_counts']}))


if __name__=='__main__':
    main()
