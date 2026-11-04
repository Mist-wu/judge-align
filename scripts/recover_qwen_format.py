#!/usr/bin/env python3
"""Recover only Qwen's observed trailing-comma serialization error, without inference."""
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from judge_align.io import digest,read_jsonl,write_jsonl
from judge_align.prompts import parse_response

def normalize_trailing_commas(text):
    out=[];quoted=False;escaped=False;removed=0
    for i,char in enumerate(text):
        if quoted:
            out.append(char)
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        else:
            if char=='"':quoted=True
            if char==',':
                j=i+1
                while j<len(text) and text[j].isspace():j+=1
                if j<len(text) and text[j] in '}]':
                    removed+=1;continue
            out.append(char)
    return ''.join(out),removed

source=Path('results/qwen.jsonl');output=Path('results/qwen-recoveries.jsonl')
rows=read_jsonl(source);recovered=read_jsonl(output)
successful={row['request_id'] for row in rows+recovered if row['status']=='success'}
commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
for row in rows:
    if row['status']!='failed' or row['request_id'] in successful or row.get('error')!='JSONDecodeError':continue
    normalized,removed=normalize_trailing_commas(row.get('raw_output') or '')
    if not removed:continue
    try:result=parse_response(normalized,row['kind'])
    except (ValueError,TypeError):continue
    recovered.append({**row,'status':'success','record_type':'format_recovery','result':result,
        'source_failure_sha256':digest(row),'source_ended_at':row['ended_at'],
        'ended_at':datetime.now(timezone.utc).isoformat(),'usage':{},'estimated_cost_usd':None,
        'normalized_output':normalized,'error':None,
        'recovery':{'method':'Remove commas immediately before closing object/array outside quoted strings only',
                    'removed_commas':removed,'git_commit':commit,'new_model_requests':0,
                    'note':'Original raw output, parse failure, and token usage remain in source ledger; no score or reason text changed.'}})
    successful.add(row['request_id'])
write_jsonl(output,recovered)
receipt={'at':datetime.now(timezone.utc).isoformat(),'source':str(source),'output':str(output),
         'format_recoveries':len(recovered),'new_model_requests':0,'status':'offline_format_processing_complete'}
Path('results/qwen-format-recovery.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
