# E4 formal execution handoff

## Running now

`exp-e4-apis.service` on `agent-01` runs Gemini **gemini-3.8-flash** and **deepseek-flash** in parallel as `exp-runner`. Each full queue contains 1,000 requests: 200 cases × 3 pointwise prompt styles plus 200 pairs × 2 orientations. Already successful records are reused. There is no request-count cap.

- Working directory: `/srv/exp-runner/repos/judge-align`
- Log: `logs/formal-api.log`
- Results: `results/gemini.jsonl`, `results/deepseek.jsonl`
- Campaign completion: `results/api-campaign.json` (written when both processes finish)
- CPU 25%, memory 256 MiB. The transient systemd unit survives SSH/Mac disconnection.
- The campaign script reads provider credentials into subprocess environments; never print `/srv/exp-runner/secrets/providers.env`.

Do not start a second copy while this unit is active. Observe with `systemctl show exp-e4-apis.service -p ActiveState -p SubState -p MemoryCurrent`; count `status=success` rows in each JSONL for progress.

## Remaining work

1. Let the full API queues finish; inspect any provider failure and resume the corresponding queue with `python3 scripts/run.py run --provider <provider> --output results/<provider>.jsonl`.
2. Root allocates the Qwen L4 runtime. Upload the repository and ignored `data/`, install `.[qwen]`, then directly run `python scripts/run.py run --provider qwen --output results/qwen.jsonl`. Download the output before releasing GPU; record CU and environment.
3. Build the full report with `python3 scripts/run.py report --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl`.
4. Run `python3 scripts/verify_completion.py` as final result accounting. It requires real raw records, not only model-written summaries.
5. Fill README and `docs/cost.md` with actual results and costs.

## Human-data boundary

The 200 primary cases have real original Empathy labels. Persona/quality/safety are different custom dimensions and remain unlabelled. Pairwise preferences and the 50-personal-item delayed retest require actual human work. No model-generated score may be labelled human. Missing human metrics remain null while automatic judging proceeds.

The source is pinned to the audited CharacterEval commit. Qwen inference uses a pinned Qwen2.5-7B-Instruct revision with Transformers NF4 on Colab. No local GPU or Mac dependency remains.
