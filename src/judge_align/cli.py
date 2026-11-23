"""Reproducible prepare -> requests -> run -> report command line."""
import argparse
import fcntl
import json
import sys
import uuid
from pathlib import Path
from .data import annotation_template,fetch,prepare,validate_annotations
from .io import append_jsonl,digest,metadata,now,read_jsonl,write_jsonl
from .ledger import ambiguous_inflight_attempts,inference_identity
from .prompts import make_requests,parse_response
from .providers import ProviderError,UnknownBillingError,estimated_cost,make_provider,resolve_model
from .report import build_report


def run_requests(config,requests,output,provider_name,retry_unknown=False,provider_factory=make_provider,reuse_prior_success=False):
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
        scoped=[request for request in requests if request['provider']==provider_name]
        seen=set()
        for request in scoped:
            if request['request_id'] in seen:
                raise ValueError(f"Duplicate request in one invocation: {request['request_id']}")
            seen.add(request['request_id'])
        existing=read_jsonl(output)
        completed={(row['request_id'],row.get('requested_model')) for row in existing if row['status']=='success'}
        identities={}
        for row in existing:
            if row['status']=='success' and 'inference_identity' in row:
                identities.setdefault((row.get('request_id'),row.get('requested_model')),[]).append(row['inference_identity'])
        failure_counts={}
        for row in existing:
            if row['status']=='failed':failure_counts[row['run_key']]=failure_counts.get(row['run_key'],0)+1
        current_identity=inference_identity(cfg)
        pending=[]
        for request in scoped:
            key=digest([request['request_id'],cfg])
            identity_key=(request['request_id'],cfg['model'])
            if identity_key in completed:
                recorded=identities.get(identity_key,[])
                if recorded and any(item!=current_identity for item in recorded) and not reuse_prior_success:
                    raise ValueError('Inference config changed since a recorded success; pass --reuse-prior-success to reuse the old result')
                continue
            related=[row for row in existing if row.get('request_id')==request['request_id'] or row.get('run_key')==key]
            if ambiguous_inflight_attempts(related) and not retry_unknown:
                raise ValueError('Unfinished provider request has unknown billing outcome; inspect ledger before --retry-unknown')
            if failure_counts.get(key,0)>=3:continue
            pending.append((key,request))
        if not pending:
            exhausted=sum((r['request_id'],cfg['model']) not in completed and failure_counts.get(digest([r['request_id'],cfg]),0)>=3 for r in scoped)
            if exhausted:raise ValueError(f'{exhausted} requests exhausted retries; investigate failures')
            return {'attempted':0,'succeeded':0,'remaining':0}
        provider=provider_factory(cfg)
        meta=metadata(config)
        attempted=succeeded=0
        for key,request in pending:
            base={k:v for k,v in request.items() if k!='messages'}
            base.update({'run_key':key,'attempt_id':uuid.uuid4().hex,'requested_model':cfg['model'],'provider_config_sha256':digest(cfg),'inference_identity':current_identity,'metadata':meta})
            append_jsonl(output,{**base,'status':'started','started_at':now()})
            attempted+=1
            usage={};model_meta={};raw=None
            try:
                raw,usage,model_meta=provider.generate(request['messages'])
                result=parse_response(raw,request['kind'])
                append_jsonl(output,{**base,'status':'success','ended_at':now(),'result':result,
                    'usage':usage,'provider_metadata':model_meta,'estimated_cost_usd':estimated_cost(usage,cfg),'raw_output':raw})
                succeeded+=1
            except UnknownBillingError:
                # Preserve the 'started' ledger state so subsequent runs refuse
                # to resend ambiguous-billing calls without --retry-unknown.
                raise
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
    run=sub.add_parser('run');run.add_argument('--config',default='configs/main.json');run.add_argument('--requests',default='data/requests.jsonl');run.add_argument('--provider',required=True);run.add_argument('--output',required=True);run.add_argument('--retry-unknown',action='store_true');run.add_argument('--reuse-prior-success',action='store_true')
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
                    pointwise_rows=[r for r in rows if r['kind']=='pointwise']
                    rows=random.Random(43).sample(pointwise_rows,min(50,len(pointwise_rows)))
                write_jsonl(args.output,rows);print(json.dumps({'annotation_tasks':len(rows)}))
        elif args.command=='run':
            cfg=json.loads(Path(args.config).read_text());rows=read_jsonl(args.requests)
            if not rows:raise ValueError('No requests; run requests first')
            outcome=run_requests(cfg,rows,args.output,args.provider,args.retry_unknown,reuse_prior_success=args.reuse_prior_success)
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
