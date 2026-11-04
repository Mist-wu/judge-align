#!/usr/bin/env python3
"""Run both full API queues; inherited provider keys never appear in argv/logs."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
env = os.environ.copy()
for raw in Path('/srv/exp-runner/secrets/providers.env').read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    if line.startswith('export '):
        line = line[7:]
    key, _, value = line.partition('=')
    parts = shlex.split(value, comments=True, posix=True)
    env[key.strip()] = parts[0] if len(parts) == 1 else value

env['PYTHONUNBUFFERED'] = '1'
started_at = datetime.now(timezone.utc).isoformat()
processes = {}
for provider in ['gemini', 'deepseek']:
    command = [sys.executable, 'scripts/run.py', 'run', '--provider', provider,
               '--output', f'results/{provider}.jsonl']
    processes[provider] = subprocess.Popen(command, cwd=ROOT, env=env)
    print(json.dumps({'provider': provider, 'status': 'running', 'pid': processes[provider].pid,
                      'started_at': started_at}), flush=True)
exit_codes = {provider: process.wait() for provider, process in processes.items()}
record = {'started_at': started_at, 'ended_at': datetime.now(timezone.utc).isoformat(),
          'exit_codes': exit_codes, 'status': 'complete' if all(code == 0 for code in exit_codes.values()) else 'failed'}
(ROOT/'results/api-campaign.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record), flush=True)
raise SystemExit(0 if record['status'] == 'complete' else 1)
