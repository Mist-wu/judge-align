#!/usr/bin/env python3
"""Attach explicit analytic hypotheses to the actual top-20 disagreement cases."""
import json
from pathlib import Path

notes=json.loads(Path('docs/case-analysis-notes.json').read_text())
lookup={row['case_id']:row for row in notes['cases']}
cases=[json.loads(line) for line in Path('results/disagreements.jsonl').read_text().splitlines()]
lines=['# 分歧最大的20个独立案例','',
       '按最大共情绝对误差排序，再按平均绝对误差、case ID排序。原文、来源行和全部评分保存在 `results/disagreements.jsonl`。',
       '', '以下为 Codex 对可见文本的分析假设，不是新的人工标注或裁决。没有改动原分、模型答案或冻结的提示。', '',
       '| 角色 / case ID | 原共情分 | 模型分范围（已观测数） | 可能机制 | 逐条分析 |',
       '|---|---:|---:|---|---|']
pending=[]
for case in cases:
    scores=[row['judge'] for row in case['judgments'] if row['dimension']=='empathy']
    note=lookup.get(case['case_id'])
    if note is None:
        pending.append(case['case_id']);note={'category':'待分析','analysis':'待根据实际案例解释，不能推定评分错误。'}
    lines.append(f"| {case['role']} / `{case['case_id']}` | {case['human_scores']['empathy']} | {min(scores)}–{max(scores)}（{len(scores)}） | {note['category']} | {note['analysis']} |")
lines += ['', '这些极端分歧案例是事后选择，不能用其类别占比估计整个数据集的错误率；不同定义、角色语境和标注噪声都可能参与形成分歧。']
Path('docs/disagreement-analysis.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'cases':len(cases),'pending_qualitative_notes':pending},ensure_ascii=False))
