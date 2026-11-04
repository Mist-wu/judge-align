# E4 formal execution handoff

## Running now

`exp-e4-apis.service` on `agent-01` continues Gemini **gemini-3.8-flash** unchanged. The separate `exp-e4-deepseek.service` resumes **deepseek-flash** with 8192 output-token capacity. Both run as `exp-runner`. Each full queue contains 1,000 requests: 200 cases × 3 pointwise prompt styles plus 200 pairs × 2 orientations. Already successful records are reused. There is no request-count cap.

- Working directory: `/srv/exp-runner/repos/judge-align`
- Logs: Gemini `logs/formal-api.log`; resumed DeepSeek `logs/formal-deepseek.log`
- Results: `results/gemini.jsonl`, `results/deepseek.jsonl`
- Receipts: original `results/api-campaign.json`; resumed DeepSeek `results/deepseek-campaign.json`. Original campaign may exit failed because its old DeepSeek child exited; inspect Gemini records and resumed DeepSeek independently.
- CPU 25%, memory 256 MiB. The transient systemd unit survives SSH/Mac disconnection.
- The campaign script reads provider credentials into subprocess environments; never print `/srv/exp-runner/secrets/providers.env`.

Do not duplicate either active provider. Refresh actual unit states and unique successful-request counts with `python3 scripts/progress.py`; snapshot is saved in `docs/formal-progress.json`. At **2026-11-04 12:05:30 UTC**, `python3 scripts/progress.py` reported both units active, Gemini **208/1000** and DeepSeek **55/1000** unique successful requests; all three earlier DeepSeek failed requests had been resolved. These are a timestamped progress snapshot, not completion. `colab ls` reported existing sessions `exp-preflight-l4`, `exp-e5-formal`, and `exp-e1-prep`: both GPU slots are occupied by E2 and E5, so do not allocate Qwen yet. Refresh with `python3 scripts/progress.py` and check GPU availability before submitting Qwen.

The requested-model and request-id pair determines whether a successful result is reused. The report records all observed provider config hashes and the 1536 → 8192 DeepSeek capacity change. Empty content now retains provider usage before being recorded as a failed parse.

Stop both workers if requested: `sudo systemctl stop exp-e4-apis.service exp-e4-deepseek.service`. A future DeepSeek-only continuation uses `/usr/bin/python3 scripts/run_api_campaign.py --provider deepseek`; supervisor supplies exp-runner identity and the same service resource limits. Do not restart the Gemini unit merely to resume DeepSeek.

## Remaining work

1. Let the full API queues finish; inspect any provider failure and resume the corresponding queue with `python3 scripts/run.py run --provider <provider> --output results/<provider>.jsonl`.
2. Root allocates the Qwen L4 runtime. Upload the repository and ignored `data/`, install `.[qwen]`, then directly run `python scripts/run.py run --provider qwen --output results/qwen.jsonl`. Download the output before releasing GPU; record CU and environment.
3. Build the full report with `python3 scripts/run.py report --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl`.
4. Run `python3 scripts/verify_completion.py` as final result accounting. It requires real raw records, not only model-written summaries.
5. Fill README and `docs/cost.md` with actual results and costs.

## Human-data boundary

The 200 primary cases have real original Empathy labels. Persona/quality/safety are different custom dimensions and remain unlabelled. Pairwise preferences and the 50-personal-item delayed retest require actual human work. No model-generated score may be labelled human. Missing human metrics remain null while automatic judging proceeds.

The source is pinned to the audited CharacterEval commit. Qwen inference uses a pinned Qwen2.5-7B-Instruct revision with Transformers NF4 on Colab. No local GPU or Mac dependency remains.
