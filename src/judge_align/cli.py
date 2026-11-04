"""Reproducible prepare -> requests -> run -> report command line."""
import argparse
import fcntl
import json
import os
import sys
from pathlib import Path
from .data import annotation_template,fetch,prepare,validate_annotations
from .io import append_jsonl,atomic_json,digest,metadata,now,read_jsonl,write_jsonl
from .prompts import make_requests,parse_response
from .providers import ProviderError,estimated_cost,make_provider,resolve_model
from .report import build_report


def run_requests(config,requests,output,provider_name,retry_unknown=False,provider_factory=make_provider):
    if provider_name not in config['providers']:
        raise ValueError('Unknown provider')
    cfg=dict(config['providers'][provider_name]);cfg['model']=resolve_model(cfg)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    lock=output.with_suffix(output.suffix+'.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise ValueError('Another process owns this output; refusing concurrent paid calls') from None
    try:
        existing=read_jsonl(output)
        states={row['run_key']:row['status'] for row in existing}
        completed={(row['request_id'],row.get('requested_model')) for row in existing if row['status']=='success'}
        failure_counts={}
        for row in existing:
            if row['status']=='failed':failure_counts[row['run_key']]=failure_counts.get(row['run_key'],0)+1
        pending=[]
        for request in requests:
            if request['provider']!=provider_name:continue
            key=digest([request['request_id'],cfg])
            if (request['request_id'],cfg['model']) in completed:continue
            if states.get(key)=='started' and not retry_unknown:
                raise ValueError('Unfinished provider request has unknown billing outcome; inspect ledger before --retry-unknown')
            if failure_counts.get(key,0)>=3:continue
            pending.append((key,request))
        if not pending:
            exhausted=sum(states.get(digest([r['request_id'],cfg]))=='failed' for r in requests if r['provider']==provider_name)
            if exhausted:raise ValueError(f'{exhausted} requests exhausted retries; investigate failures')
            return {'attempted':0,'succeeded':0,'remaining':0}
        provider=provider_factory(cfg)
        meta=metadata(config)
        attempted=succeeded=0
        for key,request in pending:
            base={k:v for k,v in request.items() if k!='messages'}
            base.update({'run_key':key,'requested_model':cfg['model'],'provider_config_sha256':digest(cfg),'metadata':meta})
            append_jsonl(output,{**base,'status':'started','started_at':now()})
            attempted+=1
            usage={};model_meta={};raw=None
            try:
                raw,usage,model_meta=provider.generate(request['messages'])
                result=parse_response(raw,request['kind'])
                append_jsonl(output,{**base,'status':'success','ended_at':now(),'result':result,
                    'usage':usage,'provider_metadata':model_meta,'estimated_cost_usd':estimated_cost(usage,cfg),'raw_output':raw})
                succeeded+=1
            except Exception as exc:
                # No untrusted exception body/URL is printed: URLs may contain credentials.
                safe_error=str(exc) if isinstance(exc,ProviderError) else type(exc).__name__
                append_jsonl(output,{**base,'status':'failed','ended_at':now(),'error':safe_error,
                    'usage':usage,'provider_metadata':model_meta,'estimated_cost_usd':estimated_cost(usage,cfg),'raw_output':raw})
                if isinstance(exc,ProviderError):
                    # Transport/auth/quota failures must not burn through all remaining calls.
                    raise
        return {'attempted':attempted,'succeeded':succeeded,'remaining':len(pending)-succeeded}
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--raw-dir',default='data/raw');prep.add_argument('--fetch',action='store_true')
    prep.add_argument('--count',type=int,default=200);prep.add_argument('--seed',type=int,default=42)
    prep.add_argument('--cases',default='data/cases.jsonl');prep.add_argument('--pairs',default='data/pairs.jsonl')
    req=sub.add_parser('requests');req.add_argument('--config',default='configs/main.json');req.add_argument('--cases',default='data/cases.jsonl');req.add_argument('--pairs',default='data/pairs.jsonl');req.add_argument('--output',default='data/requests.jsonl')
    ann=sub.add_parser('annotations');ann.add_argument('--cases',default='data/cases.jsonl');ann.add_argument('--pairs',default='data/pairs.jsonl');ann.add_argument('--output',default='data/human-template.jsonl');ann.add_argument('--validate');ann.add_argument('--round',choices=['initial','retest'],default='initial')
    run=sub.add_parser('run');run.add_argument('--config',default='configs/main.json');run.add_argument('--requests',default='data/requests.jsonl');run.add_argument('--provider',required=True);run.add_argument('--output',required=True);run.add_argument('--retry-unknown',action='store_true')
    rep=sub.add_parser('report');rep.add_argument('--config',default='configs/main.json');rep.add_argument('--cases',default='data/cases.jsonl');rep.add_argument('--pairs',default='data/pairs.jsonl');rep.add_argument('--judgments',nargs='+',required=True);rep.add_argument('--human');rep.add_argument('--outdir',default='results')
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='prepare':
            if args.fetch:fetch(args.raw_dir)
            cases,pairs=prepare(args.raw_dir,args.count,args.seed)
            write_jsonl(args.cases,cases);write_jsonl(args.pairs,pairs)
            print(json.dumps({'primary_count':sum(c['primary'] for c in cases),'total_cases':len(cases),'pairs':len(pairs),'human_measurements_absent':['persona','quality','safety','pairwise preference','delayed retest']}))
        elif args.command=='requests':
            cfg=json.loads(Path(args.config).read_text());rows=list(make_requests(read_jsonl(args.cases),read_jsonl(args.pairs),cfg['providers']))
            if not rows:raise ValueError('No input cases; run prepare first')
            write_jsonl(args.output,rows);print(json.dumps({'requests':len(rows),'paid_calls_made':0}))
        elif args.command=='annotations':
            cases,pairs=read_jsonl(args.cases),read_jsonl(args.pairs)
            if args.validate:
                rows=validate_annotations(read_jsonl(args.validate),cases,pairs);print(json.dumps({'valid_annotations':len(rows)}))
            else:
                rows=annotation_template(cases,pairs,args.round)
                if args.round=='retest':
                    # Use fixed seed, hide original scores, choose exactly 50 when available.
                    import random
                    rows=random.Random(43).sample([r for r in rows if r['kind']=='pointwise'],min(50,sum(r['kind']=='pointwise' for r in rows)))
                write_jsonl(args.output,rows);print(json.dumps({'annotation_tasks':len(rows)}))
        elif args.command=='run':
            cfg=json.loads(Path(args.config).read_text());rows=read_jsonl(args.requests)
            if not rows:raise ValueError('No requests; run requests first')
            outcome=run_requests(cfg,rows,args.output,args.provider,args.retry_unknown)
            print(json.dumps(outcome))
            if outcome['attempted']!=outcome['succeeded']:return 1
        elif args.command=='report':
            cfg=json.loads(Path(args.config).read_text())
            rows=[r for path in args.judgments for r in read_jsonl(path)]
            report=build_report(read_jsonl(args.cases),read_jsonl(args.pairs),rows,read_jsonl(args.human) if args.human else [],cfg,args.outdir)
            print(json.dumps({k:report[k] for k in ['status','automated_status','agent_review_complete','human_validation_required','primary_count','pair_count','successful_requests','expected_requests','human_labels_missing']}))
        return 0
    except (ValueError,ProviderError,FileNotFoundError,KeyError) as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
