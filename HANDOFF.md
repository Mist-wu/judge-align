# E4 formal execution handoff

Scope updated **2026-11-05 JST**; execution snapshot **2026-11-04 14:29:05 UTC / 23:29:05 JST**. All **3,000 original requests have terminal outcomes**. There are **2,970 strict-valid outputs plus one separately marked trailing-comma recovery: 2,971 analyzable outputs and 29 remaining format-invalid outputs**. E4 is **`complete`** under the user-selected automated experiment plus agent-review scope. `agent_review_complete=true`, `human_validation_complete=false`, `human_validation_required=false`; new human annotation and 48-hour retest are `not_requested`. Qwen's final artifacts have been collected, its foreground task has returned, and E2 was explicitly notified to take the GPU at 23:29:05 JST. The final analysis and standalone figures are generated; the PNG has been visually inspected. This completed E4 task needs no worker restart; other experiments and the shared GPU remain under the coordinator’s control.

## Completed API work

Each provider executed all **1,000 original requests**: 600 pointwise requests and 400 paired-orientation requests. Local final merged ledgers retain raw failures and additional attempts:

| Provider | Analyzable original IDs | Remaining format-invalid IDs | Terminal model attempts | Failed attempts |
|---|---:|---:|---:|---:|
| `deepseek-flash` | 1,000 | 0 | 1,005 | 5 |
| `gemini-3.8-flash` | 991 | 9 | 1,016 | 25 |

The two AWS units, `exp-e4-apis.service` and `exp-e4-deepseek.service`, have no worker PID and ended in failed state because recorded failures propagate their actual exit status. They are not active workers to restart. Do not issue additional API requests merely to replace format-invalid outputs. The canonical merged delivery ledgers are `results/final-delivery/deepseek.jsonl` and `results/final-delivery/gemini.jsonl`. They are synchronized through fast-forward-only Git without overwriting the original server `results/deepseek.jsonl` or `results/gemini.jsonl`. Original local exports remain under `results/original-api/`; `results/api-merge-receipt.json` records the merge and hashes. The known API list-price estimate is **$3.57763116**, plus one DeepSeek attempt with unknown usage; see `docs/cost.md`.

## Completed Qwen recovery

- Session: `exp-e24-recovery-a100`; endpoint: `gpu-a100-s-ass1b0-kysuwtw187ve`.
- Run: `E4-qwen-formal-003`; source commit: `373a1e00e84f46c6dd3f93a6483ca3e93d8939a9`.
- Model: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`; A100-SXM4-40GB, torch 2.8.0+cu128, NF4 4-bit loading and BF16 compute.
- Independent environment: `/content/e4-venv`. E2's environment and files are separate; E4 has handed model use back to E2.
- Runtime status: `/content/experiment-runs/E4-qwen-formal-003/status.json`; log: `/content/experiment-runs/E4-qwen-formal-003/output.log`.
- Runtime artifacts: `/content/experiment-runs/E4-qwen-formal-003/workspace/results/` (`qwen.jsonl`, `qwen-run.json`, `qwen-env.txt`, `qwen-drive-copy.json`).
- Durable destination: `gdrive:exp/runs/E4/E4-qwen-formal-003`; final copy verified at **14:29:04.981802 UTC**. Local downloaded originals are in `results/recovered-003/`; delivery ledgers and copied run/environment/status/Drive/merge receipts are in `results/final-delivery/`.

The old `exp-e4-qwen` assignment disappeared at approximately 13:49 UTC; it was not stopped by the E4 agent. Its recovered Drive ledger is preserved under local `results/recovered-002/` and AWS `/srv/exp-runner/state/remote/E4-qwen-formal-002-drive-recovery/`. The durable checkpoint has **641 terminal IDs (632 valid, 9 format failures)**. Only the **359 original IDs without a terminal outcome** were placed in `data/qwen-remaining-003.jsonl`, including one lost in-flight request. Existing successful and terminal format-failed outputs were excluded from regeneration.

The completed foreground launch is below for provenance, **not for duplicate submission**. Its real output connection was retained through completion.

```bash
colab exec -s exp-e24-recovery-a100 --timeout 86400 \
  -f /Users/wu/Github/judge-align/results/recovery-003-transport/foreground.py
```

Its payload ran:

```bash
/content/e4-venv/bin/python scripts/run_qwen_formal.py \
  --data-archive /content/E4-qwen-resume-data.tgz \
  --requests data/qwen-remaining-003.jsonl \
  --session exp-e24-recovery-a100 --batch-size 16 --retry-unknown
```

Recovery changes batch scheduling to size 16; the fixed model, precision, prompts, greedy decoding and output cap remain unchanged and recorded. It does not establish bit-for-bit equivalence to serial execution. Input uses left padding; token accounting excludes padding and terminates each row at its actual EOS. The first 641 terminal outputs came from serial execution. Preserve this execution change and the interruption in the final report. New malformed output remains a terminal experimental result; a nonzero process exit caused by such failures is not evidence that the original request was never executed.

The 359-request batch phase ran from **14:21:27.315849 to 14:28:53.964177 UTC**, approximately **48.2 requests/minute**. The run receipt ended at **14:28:59.153916 UTC**. All 1,000 Qwen IDs have terminal outcomes: **979 strict-valid and 21 strict-invalid**, with one already-existing trailing-comma recovery giving **980 analyzable and 20 remaining invalid**. The actual remote child exit code is **1**, reflecting retained format failures; the enclosing Colab CLI's exit code 0 must not replace it.

**The Qwen model and foreground task have ended; E2 was notified at 23:29:05 JST to load its training model. Do not release or restart this runtime.**

## Collected artifacts and reproduction

The `003` artifacts and final status have been downloaded, preserving the raw ledger and actual process exit code. The one unambiguous trailing-comma recovery is a separately marked derived record with its original failure and raw text retained. No missing fields or scores were filled, and terminal formatting failures were not regenerated. `results/final-delivery/` contains the canonical merged delivery ledgers, which keep original model attempts and derived recovery records distinct.

The final report and figures have been generated from these collected outputs. To reproduce the analysis from `/Users/wu/Github/judge-align`:

```bash
python3 scripts/run.py report \
  --judgments results/final-delivery/deepseek.jsonl \
  results/final-delivery/gemini.jsonl results/final-delivery/qwen.jsonl
python3 scripts/reconcile_cost.py --results results/final-delivery
python3 scripts/write_case_report.py
.venv/bin/python scripts/plot_results.py
.venv/bin/python -m pip freeze > results/plots-env.txt
```

Report artifacts remain `results/formal-summary.json`, `results/report.md`, and `results/selected-prompt.json`; case explanations are `docs/disagreement-analysis.md`. Figure exports are `figures/formal-comparison.png`, `.svg`, and `.pdf`. The report uses exact valid-sample denominators and discloses the failed-format count. Automatic execution and the separate agent review are complete. No further E4 model calls, new human annotation or delayed human retest are requested. Execution receipts retain their historical state labels; current completion metadata is `docs/completion-scope.json` and `results/formal-summary.json`.

## Result and human-data boundary

All 1,800 pointwise requests have already executed. DeepSeek and Gemini each have 600 analyzable pointwise outputs. Qwen has 592 strict-valid pointwise outputs, plus one separately marked trailing-comma recovery, for 593 analyzable outputs. The 193 cases valid under all nine judge/style combinations supply 36 development and 157 held-out cases after dialogue-prefix grouping across roles. The split was repaired before aggregate rankings were inspected, after case inspection; it was not preregistered.

The development rule selected **Qwen / anchored**. Held-out Empathy QWK is **0.12509, 95% CI [-0.01607, 0.25335]**; Spearman is **0.11008, 95% CI [-0.04037, 0.24729]**. Both intervals include zero. These results do not establish a reliable replacement for human scoring. Do not switch the selected prompt based on the held-out result. The 20 disagreement explanations are Codex-authored analytic hypotheses, not new human labels or adjudication.

The 200 cases retain their actual released CharacterEval Empathy scores. Per the 2026-11-05 user instruction, new **200 × 3 custom human scores, 200 × 4 human pair preferences, and 50 delayed human relabels at least 48 hours later** are **not_requested**. Their absence remains visible in `human_labels_missing`, `pairwise_human_labels_missing` and `human_retest_missing`; the original empty human fields are unchanged.

Separate agent review covers all 200 pointwise cases and 200 pairs. Two custom scores remain null and ten preference dimensions remain uncertain; 34 distinct contexts have unresolved reference-context or role/version/timepoint uncertainty. These are disclosed analytic limitations, not tasks requiring the user to annotate. The complete review artifacts, hashes and four reviewers’ findings are in `results/agent-review/` and `docs/completion-scope.json`; see `docs/agent-review.md` for provenance.

Agent ratings never enter the existing human gold, QWK, human preference accuracy, length adjustment or retest reliability. Those unavailable human-dependent measures remain null. Public-source contamination, rubric differences and format-related missingness also remain limitations. Existing formal scores and costs are unchanged. The next E4 action is optional report reproduction using the command above; no GPU submission or human work remains in the agreed scope.
