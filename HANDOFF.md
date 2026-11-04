# E4 formal execution handoff

Snapshot: **2026-11-04 14:16:39 UTC / 23:16:39 JST**. The Mac E4 agent controls this experiment; server pi is paused. Both API queues have ended. Qwen recovery `E4-qwen-formal-003` has started on the replacement A100; dependency installation is complete and model loading has been observed. First-batch throughput and final completion have not yet been observed at this snapshot.

## Completed API work

Each provider executed all **1,000 original requests**: 600 pointwise requests and 400 paired-orientation requests. Local final merged ledgers retain raw failures and additional attempts:

| Provider | Analyzable original IDs | Remaining format-invalid IDs | Terminal model attempts | Failed attempts |
|---|---:|---:|---:|---:|
| `deepseek-flash` | 1,000 | 0 | 1,005 | 5 |
| `gemini-3.8-flash` | 991 | 9 | 1,016 | 25 |

The two AWS units, `exp-e4-apis.service` and `exp-e4-deepseek.service`, have no worker PID and ended in failed state because recorded failures propagate their actual exit status. They are not active workers to restart. Do not issue additional API requests merely to replace format-invalid outputs. Keep local merged `results/deepseek.jsonl` and `results/gemini.jsonl`; copying the original server ledgers over them would discard collected retries. Original exports remain under `results/original-api/`; `results/api-merge-receipt.json` records the merge and hashes. The known API list-price estimate is **$3.57763116**, plus one DeepSeek attempt with unknown usage; see `docs/cost.md`.

## Active Qwen recovery

- Session: `exp-e24-recovery-a100`; endpoint: `gpu-a100-s-ass1b0-kysuwtw187ve`.
- Run: `E4-qwen-formal-003`; source commit: `373a1e00e84f46c6dd3f93a6483ca3e93d8939a9`.
- Model: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`; A100-SXM4-40GB, torch 2.8.0+cu128, NF4 4-bit loading and BF16 compute.
- Independent environment: `/content/e4-venv`. E2's environment and files are separate; E2 has staged its recovery and is waiting without a GPU model.
- Runtime status: `/content/experiment-runs/E4-qwen-formal-003/status.json`; log: `/content/experiment-runs/E4-qwen-formal-003/output.log`.
- Runtime artifacts: `/content/experiment-runs/E4-qwen-formal-003/workspace/results/` (`qwen.jsonl`, `qwen-run.json`, `qwen-env.txt`, `qwen-drive-copy.json`).
- Durable destination: `gdrive:exp/runs/E4/E4-qwen-formal-003`; checkpoints every 120 seconds and at exit.

The old `exp-e4-qwen` assignment disappeared at approximately 13:49 UTC; it was not stopped by the E4 agent. Its recovered Drive ledger is preserved under local `results/recovered-002/` and AWS `/srv/exp-runner/state/remote/E4-qwen-formal-002-drive-recovery/`. The durable checkpoint has **641 terminal IDs (632 valid, 9 format failures)**. Only the **359 original IDs without a terminal outcome** are in `data/qwen-remaining-003.jsonl`, including one lost in-flight request. Existing successful and terminal format-failed outputs are excluded from regeneration.

The already-submitted foreground launch is below for provenance, **not for duplicate submission**. Keep its real output connection attached until the task ends.

```bash
colab exec -s exp-e24-recovery-a100 --timeout 86400 \
  -f /Users/wu/Github/judge-align/results/recovery-003-transport/foreground.py
```

Its payload runs:

```bash
/content/e4-venv/bin/python scripts/run_qwen_formal.py \
  --data-archive /content/E4-qwen-resume-data.tgz \
  --requests data/qwen-remaining-003.jsonl \
  --session exp-e24-recovery-a100 --batch-size 16 --retry-unknown
```

Recovery changes batch scheduling to size 16; the fixed model, precision, prompts, greedy decoding and output cap remain unchanged and recorded. It does not establish bit-for-bit equivalence to serial execution. Input uses left padding; token accounting excludes padding and terminates each row at its actual EOS. The first 641 terminal outputs came from serial execution. Preserve this execution change and the interruption in the final report. New malformed output remains a terminal experimental result; a nonzero process exit caused by such failures is not evidence that the original request was never executed.

**When the remaining requests finish, confirm the Qwen model process and foreground task have ended and immediately notify E2 and the coordinator. Do not release or restart this runtime.** E2 then loads its training model in its own environment.

## Collection and final analysis

Collect the `003` artifact directory and final status, retaining the original raw ledger and actual process exit code. Confirm that all 1,000 original Qwen IDs have terminal outcomes; successful formatting is a separate rate, not the execution-completion condition. Preserve any obvious syntax recovery as a separately marked derived record with its original failure and raw text. Do not fill missing fields or scores, and do not generate replacement judgments.

After collection and the documented merge, the next analysis commands from `/Users/wu/Github/judge-align` are:

```bash
python3 scripts/run.py report \
  --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl
python3 scripts/reconcile_cost.py
python3 scripts/write_case_report.py
.venv/bin/python scripts/plot_results.py
.venv/bin/python -m pip freeze > results/plots-env.txt
```

The report command above assumes any separately marked, unambiguous format-recovery records have been included once in the merged Qwen ledger. Inspect the rendered `figures/formal-comparison.png` and preserve `.svg`/`.pdf` exports. Deliver `results/formal-summary.json`, `results/report.md`, `results/selected-prompt.json`, final ledgers/receipts, the figures, `docs/disagreement-analysis.md`, and updated README/cost/status documents. No separate smoke-test or verification gate is required. Completion means all **3,000 scheduled requests have terminal outcomes**, with failed-format counts and valid-sample denominators disclosed; the human work below remains pending.

## Result and human-data boundary

All 1,800 pointwise requests have already executed. DeepSeek and Gemini each have 600 analyzable pointwise outputs. Qwen has 592 strict-valid pointwise outputs, plus one separately marked trailing-comma recovery, for 593 analyzable outputs. The 193 cases valid under all nine judge/style combinations supply 36 development and 157 held-out cases after dialogue-prefix grouping across roles. The split was repaired before aggregate rankings were inspected, after case inspection; it was not preregistered.

The development rule selected **Qwen / anchored**. Held-out Empathy QWK is **0.12509, 95% CI [-0.01607, 0.25335]**; Spearman is **0.11008, 95% CI [-0.04037, 0.24729]**. Both intervals include zero. These results do not establish a reliable replacement for human scoring. Do not switch the selected prompt based on the held-out result. The 20 disagreement explanations are Codex-authored analytic hypotheses, not new human labels or adjudication.

The 200 cases have actual released CharacterEval Empathy scores. Still pending are **200 × 3 custom persona/quality/safety scores, 200 × 4 same-context pair preferences, and 50 delayed human relabels at least 48 hours later**. Length-bias adjustment that requires independent human quality scores remains unavailable. Never label model-generated ratings as human work. Public-source contamination, rubric differences and format-related missingness remain limitations even when automatic execution finishes.
