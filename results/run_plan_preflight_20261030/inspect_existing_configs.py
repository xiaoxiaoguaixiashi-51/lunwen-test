"""Read-only inspection recipe for the already configured cloud instance."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))
from scripts.preflight_kcf_run_plan import audit_plan

plan = json.loads(Path('/root/autodl-tmp/formal-draft-plan-20261030.json').read_text())
mapping = {'Full': 'kcf_full.yaml', 'A1': 'kcf_a1.yaml', 'A2': 'kcf_full.yaml',
           'A3': 'kcf_a3.yaml', 'RAG': 'kcf_full.yaml'}
for job in plan['jobs']:
    job['config'] = str(Path('config/private', mapping[job['arm']]).resolve())
paths = {Path(job['config']) for job in plan['jobs']}
before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
with patch('socket.socket', side_effect=AssertionError('network prohibited')), patch(
        'sqlite3.connect', side_effect=AssertionError('ledger mutation prohibited')):
    result = audit_plan(plan)
after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
if before != after:
    raise RuntimeError('Existing configuration changed during inspection')
result['existing_private_configs_unchanged'] = True
Path('/root/autodl-tmp/current-config-plan-preflight-20261030.json').write_text(json.dumps(result, indent=2) + '\n')
Path('/root/autodl-tmp/current-config-draft-plan-20261030.json').write_text(json.dumps(plan, indent=2) + '\n')
print(json.dumps({'configuration_checks_passed': result['configuration_checks_passed'],
                  'issues': result['issues'], 'existing_private_configs_unchanged': True}))
