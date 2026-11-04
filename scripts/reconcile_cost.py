#!/usr/bin/env python3
"""Reconcile recorded E4 API usage against the prices observed on 2026-11-04."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--results', default='results')
args = parser.parse_args()
root = Path(args.results)
providers = {}
for name in ('deepseek', 'gemini'):
    rows = [json.loads(line) for line in (root / f'{name}.jsonl').read_text().splitlines()]
    totals = Counter()
    states = {}
    estimate = 0.0
    unknown = 0
    for row in rows:
        states[row['run_key']] = row['status']
        if row['status'] not in ('success', 'failed'):
            continue
        totals['terminal_attempts'] += 1
        totals[row['status'] + '_attempts'] += 1
        usage = row.get('usage') or {}
        if 'input_tokens' not in usage or 'output_tokens' not in usage:
            unknown += 1
            continue
        prompt = usage['input_tokens']
        output = usage['output_tokens']
        cached = usage.get('cached_input_tokens', 0)
        thoughts = usage.get('thought_tokens', 0)
        totals.update(input_tokens=prompt, output_tokens=output,
                      cached_input_tokens=cached, additional_thinking_tokens=thoughts)
        ended = datetime.fromisoformat(row['ended_at'].replace('Z', '+00:00'))
        # All actual campaign calls occur after the published weekday peak window.
        # This historical reconciliation deliberately does not guess future prices.
        if ended.date().isoformat() != '2026-11-04' or ended.hour < 10:
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
                       'currently_inflight_attempts': sum(s == 'started' for s in states.values())}
report = {
    'created_at': datetime.now(timezone.utc).isoformat(),
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
