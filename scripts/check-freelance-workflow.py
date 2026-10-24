"""Structural and credential-boundary checks, not an n8n runtime substitute."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
w=json.loads((root/'n8n/freelance-agency.json').read_text())
nodes={n['name']:n for n in w['nodes']}
assert len(nodes)==len(w['nodes'])
assert not w['active']
assert len([n for n in nodes.values() if n['type'].endswith('formTrigger')])==1
assert nodes['Freelance control centre']['parameters']['authentication']=='basicAuth'
assert nodes['Freelance control centre']['parameters']['responseMode']=='lastNode'
for source,values in w['connections'].items():
 assert source in nodes
 for port in values['main']:
  for target in port: assert target['node'] in nodes
for n in nodes.values():
 if n['type'].endswith('httpRequest'):
  assert n['parameters']['authentication']=='genericCredentialType'
  role=n['credentials']['httpHeaderAuth']['name']
  assert role==('Ops Pilot Owner' if n['name']=='Owner decision · explicit review' else 'Ops Pilot Workflow')
  assert n.get('retryOnFail') is False
  assert n['parameters']['url'].lstrip('=').startswith('http://127.0.0.1:8767/bridge/')
for name in ['01 · Scout','02 · Evaluator','03 · Manager','04 · Client assistant','05 · Proposal writer','06 · DevOps worker','07 · Reviewer','08 · Delivery assistant','09 · Earnings tracker']:
 assert name in nodes
assert 'pinData' in w and not w['pinData']
print('Workflow structure and credential boundaries passed (23 nodes, 9 roles).')
