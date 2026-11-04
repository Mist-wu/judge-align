#!/usr/bin/env python3
"""Check actual formal records and pinned data; smoke outputs cannot pass."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from judge_align.data import SOURCE_COMMIT,prepare
from judge_align.io import digest,read_jsonl
from judge_align.prompts import make_requests,parse_response
root=Path(__file__).resolve().parents[1]
summary_path=root/'results/formal-summary.json'
if not summary_path.exists():
    raise SystemExit('BLOCKED: formal judgments have not been run')
s=json.loads(summary_path.read_text())
cfg=json.loads((root/'configs/main.json').read_text())
cases=read_jsonl(root/'data/cases.jsonl');pairs=read_jsonl(root/'data/pairs.jsonl')
manifest=json.loads((root/'docs/data-source-manifest.json').read_text())
assert manifest['commit']==SOURCE_COMMIT
for entry in manifest['files']:
    payload=(root/'data/raw'/entry['file']).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==entry['sha256'],'Pinned source hash mismatch'
expected_cases,expected_pairs=prepare(root/'data/raw',200,cfg['seed'])
assert digest(cases)==digest(expected_cases) and digest(pairs)==digest(expected_pairs),'Prepared cases differ from pinned-source sample'
requests={r['request_id']:r for r in make_requests(cases,pairs,cfg['providers'])}
judgments=[];successful={}
for provider in cfg['providers']:
    rows=read_jsonl(root/f'results/{provider}.jsonl');judgments.extend(rows)
    selected=[r for r in rows if r.get('status')=='success']
    ids=set()
    for row in selected:
        assert row['provider']==provider,'Wrong provider file'
        request=requests[row['request_id']]
        assert request['provider']==provider,'Unknown request provider'
        assert row['item_id']==request['item_id'] and row['style']==request['style'],'Wrong case/style'
        assert row.get('swapped',False)==request.get('swapped',False),'Wrong pair orientation'
        assert row['requested_model']==cfg['providers'][provider]['model'],'Different model run'
        assert row.get('provider_metadata',{}).get('model'),'Missing actual provider metadata'
        if provider=='qwen':
            assert row['provider_metadata'].get('gpu') and row['provider_metadata'].get('cuda'),'Qwen requires real GPU provenance'
        assert row.get('usage',{}).get('input_tokens',0)>0,'Missing real usage'
        assert parse_response(row['raw_output'],row['kind'])==row['result'],'Result differs from actual provider output'
        ids.add(row['request_id']);successful[row['request_id']]=row
    assert len(ids)==1000,f'Incomplete provider {provider}'
assert s['run_kind']=='formal' and s['automated_status']=='complete','Formal automated run incomplete'
assert s['source_commit']==SOURCE_COMMIT,'Unknown data provenance'
assert s['primary_count']==200 and s['pair_count']==200,'Need 200 primary cases and pairs'
assert len(successful)==s['successful_requests']==s['expected_requests']==3000,'Incomplete requests'
assert s['data_sha256']==digest(cases) and s['judgments_sha256']==digest(judgments),'Report does not match raw results'
assert s['config_sha256']==digest(cfg),'Report config has changed'
assert all(r['qwk']['n']==200 for r in s['pointwise'] if r['dimension']=='empathy'),'Missing real human Empathy comparisons'
assert all(r['position_inconsistency']['n']==200 for r in s['pairwise']),'Incomplete orientation pairs'
for path in ['README.md','docs/baselines.md','docs/cost.md','results/report.md','results/kappa.svg','results/disagreements.jsonl']:
    assert (root/path).stat().st_size>0,f'Missing artifact: {path}'
print(json.dumps({'automated':'complete','human_pending':s['human_pending'],'pairwise_human_pending':s['pairwise_human_pending'],'retest_pending':s['retest_pending']}))
