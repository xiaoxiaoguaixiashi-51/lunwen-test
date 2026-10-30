"""Capture F0/F1/F2 first analysis prompts offline; never creates a provider client."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.agents.task_agent import TaskAgent, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from scripts.minimal_source_context import build_context


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokenizer',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    protocol_path=repo/'experiments/protocols/kcf_rerun_v1.json'
    protocol=json.loads(protocol_path.read_text())
    method_file=repo/protocol['method_list']
    if hashlib.sha256(method_file.read_bytes()).hexdigest()!=protocol['method_list_sha256']:
        raise ValueError('Frozen method manifest changed')
    if hashlib.sha256(args.tokenizer.read_bytes()).hexdigest()!=protocol['tokenizer_sha256']:
        raise ValueError('Tokenizer changed')
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(args.tokenizer))
    root=args.output_dir.resolve()
    root.mkdir(parents=True,exist_ok=False)
    rows=[]
    for method in json.loads(method_file.read_text()):
        class Capture:
            def generate(self,system,user,**kwargs):
                self.messages=[{'role':'system','content':system},{'role':'user','content':user}]
                return '{}'
        capture=Capture()
        row={'id':method['id'],'project_id':method['project_id'],'source_sha256':method['source_sha256']}
        def count(messages):
            return protocol['budget']['framing_reserve']+sum(len(tokenizer.encode(message['content'],add_special_tokens=False).ids) for message in messages)
        try:
            with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
                analysis=TaskAgent(llm_client=capture).analyze(method['target'],method['method'],
                    method_owner=method['method_owner'],method_parameter_types=method['method_parameter_types'])
                row['estimated_first_input_with_reserve']={'F0':count(capture.messages)}
                row['blocked']={'F0':count(capture.messages)>protocol['budget']['max_input_tokens_per_call']}
                def messages(context):
                    user=USER_PROMPT_TEMPLATE.format(source_code=context,
                        ast_analysis=json.dumps(analysis['static_analysis'],indent=2,ensure_ascii=False))
                    return [{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':user}]
                context=build_context(method,lambda text:count(messages(text))<=protocol['budget']['max_input_tokens_per_call'])
            row['estimated_first_input_with_reserve']={'F0':count(capture.messages),'F1':count(messages(context['F1'])),
                                                       'F2':count(messages(context['F2']))}
            row['blocked']={key:value>protocol['budget']['max_input_tokens_per_call'] for key,value in row['estimated_first_input_with_reserve'].items()}
            row['focal_ast_roundtrip_verified']=True
            row['focal_sha256']=context['focal_sha256']
            row['included_local_helpers']=context['included_local_helpers']
            row['excluded_local_helpers']=context['excluded_local_helpers']
            path=root/(method['id']+'.json')
            path.write_text(json.dumps(context,indent=2)+'\n')
            row['context_file_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception as exc:
            row['error_type']=type(exc).__name__
            row['error_message']=str(exc)[:200]
        rows.append(row)
    result={'kind':'offline_source_context_baselines_not_generation_or_novelty_results','api_calls':0,
        'protocol_id':protocol['protocol_id'],'tokenizer_sha256':protocol['tokenizer_sha256'],
        'input_ceiling':protocol['budget']['max_input_tokens_per_call'],'targets':len(rows),
        'successful_context_extractions':sum(row.get('focal_ast_roundtrip_verified',False) for row in rows),
        'blocked_first_prompts':{key:sum(row.get('blocked',{}).get(key,False) for row in rows) for key in ['F0','F1','F2']},
        'method_list_sha256':protocol['method_list_sha256'],'rows':rows,
        'implementation_sha256':{name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in
            ['scripts/minimal_source_context.py','scripts/audit_minimal_source_context.py','src/agents/task_agent.py','src/utils/focal_target.py']},
        'limits':['Only the first TaskAgent prompt is measured; later pipeline prompts not validated.',
                  'No claims that dependency information, behavior or compilation are preserved by context omission.',
                  'No pipeline integration, model requests, project tests, generated tests or evaluation answers used.',
                  'Simple source selection is a baseline, not a new contribution.']}
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ['targets','successful_context_extractions','blocked_first_prompts','api_calls']}))


if __name__=='__main__':main()
