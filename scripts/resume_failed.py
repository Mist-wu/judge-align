#!/usr/bin/env python3
"""Continue terminal format failures from a running formal API campaign snapshot."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--provider',required=True,choices=['gemini','deepseek'])
parser.add_argument('--env-file',required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1];os.chdir(root)
sys.path.insert(0, str(root / 'src'))
from judge_align.io import read_jsonl, write_jsonl
base=read_jsonl(root/f'results/{args.provider}.jsonl')
target=root/f'results/{args.provider}-retries.jsonl'
retry=read_jsonl(target)
successful={row['request_id'] for row in base+retry if row['status']=='success'}
latest={row['request_id']:row for row in base+retry}
ids={key for key,row in latest.items() if row['status']=='failed'
     and row.get('error') in {'JSONDecodeError','ValueError'} and key not in successful}
selected=[row for row in read_jsonl(root/'data/requests.jsonl') if row['provider']==args.provider and row['request_id'] in ids]
if not selected:
    print(json.dumps({'provider':args.provider,'format_failures_to_resume':0}));raise SystemExit(0)
if args.provider=='gemini' and any(row['kind']!='pairwise' for row in selected):
    raise SystemExit('This Gemini continuation schema is specifically for the observed pairwise failures.')
seen={json.dumps(row,sort_keys=True,ensure_ascii=False) for row in retry}
with target.open('a') as stream:
    for row in base:
        identity=json.dumps(row,sort_keys=True,ensure_ascii=False)
        if row['request_id'] in ids and identity not in seen:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');seen.add(identity)
requests=root/f'data/{args.provider}-terminal-failed.jsonl'
write_jsonl(requests, selected)
config='configs/gemini-pairwise-continuation.json' if args.provider=='gemini' else 'configs/main.json'
env=os.environ.copy()
for raw in Path(args.env_file).read_text().splitlines():
    line=raw.strip()
    if not line or line.startswith('#'):continue
    if line.startswith('export '):line=line[7:]
    key,_,value=line.partition('=');parts=shlex.split(value,comments=True,posix=True)
    env[key.strip()]=parts[0] if len(parts)==1 else value
command=[sys.executable,'scripts/run.py','run','--provider',args.provider,'--config',config,
         '--requests',str(requests),'--output',str(target)]
started=datetime.now(timezone.utc)
receipt={'started_at':started.isoformat(),'provider':args.provider,'request_ids':sorted(ids),
         'command':command,'purpose':'Terminal format failures only; original worker has already passed these IDs'}
print(json.dumps({'provider':args.provider,'format_failures_to_resume':len(selected)}),flush=True)
receipt['exit_code']=subprocess.run(command,env=env).returncode
receipt['ended_at']=datetime.now(timezone.utc).isoformat()
(root/f'results/formal-retry-{args.provider}-{started:%Y%m%dT%H%M%SZ}.json').write_text(json.dumps(receipt,indent=2)+'\n')
raise SystemExit(receipt['exit_code'])
