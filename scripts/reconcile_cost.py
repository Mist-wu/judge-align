#!/usr/bin/env python3
"""Reconcile recorded E4 API usage against the prices observed on 2026-11-04."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from judge_align.io import now
from judge_align.ledger import ambiguous_inflight_attempts

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--results', default='results')
args = parser.parse_args()
root = Path(args.results)
window_start = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
window_end = datetime(2026, 11, 5, tzinfo=timezone.utc)
providers = {}
for name in ('deepseek', 'gemini'):
    rows = [json.loads(line) for line in (root / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    totals = Counter()
    estimate = 0.0
    unknown = 0
    for row in rows:
        if row['status'] not in ('success', 'failed') or row.get('record_type')=='format_recovery':
            continue
        totals['terminal_attempts'] += 1
        totals[row['status'] + '_attempts'] += 1
        usage = row.get('usage') or {}
        prompt = usage.get('input_tokens')
        output = usage.get('output_tokens')
        if prompt is None or output is None:
            unknown += 1
            continue
        cached = usage.get('cached_input_tokens') or 0
        thoughts = usage.get('thought_tokens') or 0
        totals.update(input_tokens=prompt, output_tokens=output,
                      cached_input_tokens=cached, additional_thinking_tokens=thoughts)
        if cached < 0 or cached > prompt:
            unknown += 1
            continue
        ended = datetime.fromisoformat(row['ended_at'].replace('Z', '+00:00'))
        # All actual campaign calls occur after the published weekday peak window.
        # This historical reconciliation deliberately does not guess future prices.
        if ended.tzinfo is None or not window_start <= ended < window_end:
            unknown += 1
            continue
        if name == 'deepseek' and row['requested_model'] == 'deepseek-flash':
            # DeepSeek completion_tokens already includes its reasoning tokens.
            estimate += ((prompt-cached)*0.15 + cached*0.003 + output*0.60) / 1_000_000
        elif name == 'gemini' and row['requested_model'] == 'gemini-3.8-flash':
            estimate += ((prompt-cached)*0.75 + cached*0.075 + (output+thoughts)*3.75) / 1_000_000
        else:
            unknown += 1
    providers[name] = {**totals, 'estimated_paid_list_usd': round(estimate, 8),
                       'unknown_cost_terminal_attempts': unknown,
                       'currently_inflight_attempts': ambiguous_inflight_attempts(rows)}
report = {
    'created_at': now(),
    'pricing_verified_at': '2026-11-04',
    'pricing_scope': '2026-11-04 10:00-24:00 UTC; standard paid Gemini and off-peak DeepSeek',
    'providers': providers,
    'known_estimated_paid_list_usd': round(sum(p['estimated_paid_list_usd'] for p in providers.values()), 8),
    'sources': ['https://aistudio.google.com/docs/pricing#gemini-3.8-flash',
                'https://api-docs.deepseek.com/quick_start/pricing/'],
    'limitations': ['List-price estimate, not an invoice; Gemini account free-tier status is unknown.',
                    'Missing provider usage and unfinished calls have unknown cost, not zero.',
                    'Qwen Colab compute units are accounted separately from API dollars.']}
(root / 'cost-summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
