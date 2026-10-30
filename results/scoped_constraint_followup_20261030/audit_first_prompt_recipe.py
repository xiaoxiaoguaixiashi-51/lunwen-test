"""Offline first-prompt feasibility on the frozen 41 methods. No model client."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, '/root/lunwen-test')
from tokenizers import Tokenizer
from src.agents.task_agent import TaskAgent

repo=Path('/root/lunwen-test')
protocol=json.loads((repo/'experiments/protocols/kcf_rerun_v1.json').read_text())
manifest=repo/protocol['method_list']
if hashlib.sha256(manifest.read_bytes()).hexdigest()!=protocol['method_list_sha256']:
    raise RuntimeError('Method list changed')
tokenizer_file=Path('/root/autodl-tmp/budget-smoke-v2-20261030/tokenizer.json')
if hashlib.sha256(tokenizer_file.read_bytes()).hexdigest()!=protocol['tokenizer_sha256']:
    raise RuntimeError('Tokenizer changed')
tokenizer=Tokenizer.from_file(str(tokenizer_file))
rows=[]
for method in json.loads(manifest.read_text()):
    target=Path(method['target'])
    if hashlib.sha256(target.read_bytes()).hexdigest()!=method['source_sha256']:
        raise RuntimeError('Source changed')
    class Capture:
        def generate(self,system,user,**kwargs):
            messages=[{'role':'system','content':system},{'role':'user','content':user}]
            estimate=protocol['budget']['framing_reserve']+sum(len(tokenizer.encode(m['content'],add_special_tokens=False).ids) for m in messages)
            rows.append({'id':method['id'],'project_id':method['project_id'],'fqcn':method['fqcn'],
                'source_sha256':method['source_sha256'],'estimated_input_with_reserve':estimate,
                'would_be_blocked_by_frozen_input_ceiling':estimate>protocol['budget']['max_input_tokens_per_call'],
                'prompt_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()})
            return '{}'
    try:
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            TaskAgent(llm_client=Capture()).analyze(str(target),method['method'],
                method_owner=method['method_owner'],method_parameter_types=method['method_parameter_types'])
    except Exception as exc:
        rows.append({'id':method['id'],'project_id':method['project_id'],'fqcn':method['fqcn'],
                     'static_analysis_error_type':type(exc).__name__})
result={'kind':'offline_first_task_prompt_preflight_not_provider_usage_or_generation_results','api_calls':0,
    'protocol_id':protocol['protocol_id'],'input_ceiling':protocol['budget']['max_input_tokens_per_call'],
    'tokenizer_sha256':protocol['tokenizer_sha256'],'rows':rows,
    'blocked_first_prompts':sum(r.get('would_be_blocked_by_frozen_input_ceiling',False) for r in rows),
    'static_analysis_errors':sum('static_analysis_error_type' in r for r in rows),
    'notes':['Only the first TaskAgent prompt; passing it does not prove later prompts fit.',
             'Dummy response is used only after capturing the actual first prompt. No LLMClient or provider SDK is constructed.']}
destination=Path('/root/autodl-tmp/full_first_prompt_preflight_20261030.json')
with destination.open('x') as handle: handle.write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'targets':len(rows),'blocked_first_prompts':result['blocked_first_prompts'],'static_analysis_errors':result['static_analysis_errors'],'api_calls':0}))
