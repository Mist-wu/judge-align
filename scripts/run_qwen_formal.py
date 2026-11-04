#!/usr/bin/env python3
"""Install GPU dependencies and execute the entire Qwen queue with Drive copies."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

parser=argparse.ArgumentParser()
parser.add_argument('--data-archive',required=True)
args=parser.parse_args()
root=Path.cwd();results=root/'results';results.mkdir(exist_ok=True)
run_id=os.environ.get('EXPERIMENT_RUN_ID','E4-qwen-formal-001')
receipt={'run_id':run_id,'session':'exp-e4-qwen','started_at':datetime.now(timezone.utc).isoformat(),
         'model':'Qwen/Qwen2.5-7B-Instruct','revision':'a09a35458c702b33eeacc393d103063234e8bc28',
         'target_requests':1000,'state':'installing','commit':os.environ.get('EXPERIMENT_COMMIT')}
receipt_path=results/'qwen-run.json'
def save():receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
def checkpoint():
    command=[sys.executable,'-m','exp_common.checkpoint','--source',str(results),
             '--experiment','E4','--run-id',run_id,'--receipt',str(results/'qwen-drive-copy.json')]
    code=subprocess.run(command).returncode
    print(json.dumps({'checkpoint_exit_code':code,'at':datetime.now(timezone.utc).isoformat()}),flush=True)
    return code
save()
with tarfile.open(args.data_archive) as archive:archive.extractall(root,filter='data')
install=subprocess.run([sys.executable,'-m','pip','install','-e','.[qwen]'])
if install.returncode:
    receipt.update(state='dependency_failed',returncode=install.returncode);save();checkpoint()
    raise SystemExit(install.returncode)
import torch
receipt['hardware']={'gpu':torch.cuda.get_device_name(),'gpu_memory_bytes':torch.cuda.get_device_properties(0).total_memory,
                     'torch':torch.__version__,'cuda':torch.version.cuda,'quantization':'bitsandbytes NF4 4-bit'}
(results/'qwen-env.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
receipt.update(state='running');save()
print(json.dumps(receipt),flush=True)
process=subprocess.Popen([sys.executable,'scripts/run.py','run','--provider','qwen','--output','results/qwen.jsonl'])
while True:
    try:
        code=process.wait(timeout=120)
        break
    except subprocess.TimeoutExpired:
        checkpoint()
receipt.update(state='succeeded' if code==0 else 'failed',returncode=code,ended_at=datetime.now(timezone.utc).isoformat())
path=results/'qwen.jsonl'
if path.exists():
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    receipt['successful_requests']=len({r['request_id'] for r in rows if r['status']=='success'})
    receipt['failed_attempts']=sum(r['status']=='failed' for r in rows)
save();checkpoint()
print(json.dumps(receipt),flush=True)
raise SystemExit(code)
