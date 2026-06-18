import json
from pathlib import Path

raw = Path('data/raw')
rgs = {'LIVE': set(), 'MOCK': set()}

for p in raw.glob('*_latest.json'):
    d = json.loads(p.read_text('utf-8'))
    is_live = d.get('metadata', {}).get('source') == 'live'
    cat = 'LIVE' if is_live else 'MOCK'
    
    # Extract RGs based on known schema
    for r in d.get('records', []):
        if 'resourceGroup' in r: rgs[cat].add(r['resourceGroup'])
    for r in d.get('recommendations', []):
        if 'resourceGroup' in r: rgs[cat].add(r['resourceGroup'])
    for r in d.get('unattachedDisks', []) + d.get('publicIps', []) + d.get('resourceInventory', []):
        if 'resourceGroup' in r: rgs[cat].add(r['resourceGroup'])
    for r in d.get('nodes', []):
        if 'resourceGroup' in r: rgs[cat].add(r['resourceGroup'])
    for r in d.get('metrics', []):
        if 'resourceGroup' in r: rgs[cat].add(r['resourceGroup'])

print('Resource Groups from LIVE Azure APIs (Cost, ResourceGraph, Advisor):')
print('  ' + ', '.join(rgs['LIVE']) if rgs['LIVE'] else '  None found')
print('\nResource Groups from MOCK Local Files (AKS, VM Metrics):')
print('  ' + ', '.join(rgs['MOCK']) if rgs['MOCK'] else '  None found')
