#!/usr/bin/env python3
"""Snapshot actual formal API records and current worker units."""
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
units = {}
for name in ['exp-e4-apis.service', 'exp-e4-deepseek.service']:
    command = ['systemctl', 'show', name, '-p', 'ActiveState', '-p', 'SubState', '-p', 'MemoryCurrent', '-p', 'MainPID']
    result = subprocess.run(command, capture_output=True, text=True)
    units[name] = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
providers = {}
for name in ['gemini', 'deepseek']:
    path = root/f'results/{name}.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines(keepends=True) if line.endswith('\n')]
    successful = {(r['request_id'],r.get('requested_model')) for r in rows if r['status'] == 'success'}
    failed = [r for r in rows if r['status'] == 'failed']
    unresolved = {(r['request_id'],r.get('requested_model')) for r in failed} - successful
    latest = next((r for r in reversed(rows) if r['status'] == 'success'), None)
    providers[name] = {'successful_requests':len(successful), 'target_requests':1000,
                       'failed_attempts':len(failed), 'unresolved_failed_requests':len(unresolved),
                       'latest_success_at':latest['ended_at'] if latest else None,
                       'result_path':str(path)}
snapshot = {'snapshot_at':datetime.now(timezone.utc).isoformat(), 'status':'progress_snapshot_not_completion',
            'units':units,'providers':providers,
            'logs':[str(root/'logs/formal-api.log'),str(root/'logs/formal-deepseek.log')],
            'refresh_command':'python3 scripts/progress.py',
            'report_command':'python3 scripts/run.py report --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl',
            'qwen_status':'not started; requires separately allocated GPU',
            'note':'exp-e4-apis may eventually exit failed because its original DeepSeek child failed; independent resumed DeepSeek is exp-e4-deepseek.'}
(root/'docs/formal-progress.json').write_text(json.dumps(snapshot,indent=2)+'\n')
print(json.dumps(snapshot,ensure_ascii=False))
