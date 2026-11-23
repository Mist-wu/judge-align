#!/usr/bin/env python3
"""Execute only the remaining original Qwen requests in batches after preemption."""
import argparse
from pathlib import Path
import sys
import json
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from judge_align.io import append_jsonl,digest,metadata,now,read_jsonl
from judge_align.ledger import inference_identity
from judge_align.prompts import parse_response
from judge_align.providers import QwenProvider

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config',default='configs/main.json')
parser.add_argument('--requests',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--batch-size',type=int,default=16)
parser.add_argument('--retry-unknown',action='store_true')
parser.add_argument('--reuse-prior-success',action='store_true')
args=parser.parse_args()
config=json.loads(Path(args.config).read_text());cfg=dict(config['providers']['qwen'])
cfg['inference_batch_size']=args.batch_size
existing=read_jsonl(args.output)
terminal={row['request_id'] for row in existing if row['status'] in {'success','failed'}}
started={row['request_id'] for row in existing if row['status']=='started'}-terminal
requests=[row for row in read_jsonl(args.requests) if row['provider']=='qwen' and row['request_id'] not in terminal]
if len(requests)!=len({row['request_id'] for row in requests}):
    raise SystemExit('Duplicate request in one invocation')
if started.intersection(row['request_id'] for row in requests) and not args.retry_unknown:
    raise SystemExit('Lost in-flight rows require explicit --retry-unknown after confirming the old session is gone.')
current=inference_identity(cfg)
if not args.reuse_prior_success:
    for row in existing:
        if row.get('status')=='success' and 'inference_identity' in row and row['inference_identity']!=current:
            raise SystemExit('Inference config changed since a recorded success; pass --reuse-prior-success to reuse the old result')
provider=QwenProvider(cfg);meta=metadata(config);completed=failed=0
for offset in range(0,len(requests),args.batch_size):
    batch=requests[offset:offset+args.batch_size];bases=[]
    for request in batch:
        base={key:value for key,value in request.items() if key!='messages'}
        base.update(run_key=digest([request['request_id'],cfg]),attempt_id=uuid.uuid4().hex,
                    requested_model=cfg['model'],provider_config_sha256=digest(cfg),
                    inference_identity=current,metadata=meta)
        bases.append(base);append_jsonl(args.output,{**base,'status':'started','started_at':now()})
    answers=provider.generate_batch([row['messages'] for row in batch])
    for request,base,(raw,usage,model_meta) in zip(batch,bases,answers):
        record={**base,'ended_at':now(),'raw_output':raw,'usage':usage,
                'provider_metadata':model_meta,'estimated_cost_usd':None}
        try:
            result=parse_response(raw,request['kind'])
            append_jsonl(args.output,{**record,'status':'success','result':result})
        except ValueError as error:
            append_jsonl(args.output,{**record,'status':'failed','error':type(error).__name__});failed+=1
        completed+=1
    print(json.dumps({'completed_remaining_requests':completed,'remaining_request_total':len(requests),
                      'format_failures':failed,'batch_size':len(batch),'at':now()}),flush=True)
raise SystemExit(1 if failed else 0)
