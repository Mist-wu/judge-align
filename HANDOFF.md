# E4 handoff

## Current state

Implementation and 22 offline tests are ready. **AWS API smoke passed: one Gemini 3.8-flash request and one DeepSeek flash request, no GPU work.** Raw success records are in both local and server `results/`; continuation skips these exact requests. Full experiment remains incomplete. Real source data have been downloaded locally. 200 primary cases, 200 same-context pairs, 3,000 requests and blinded annotation templates were generated. These ignored files need separate synchronization or regeneration on the server.

- Provider defaults: DeepSeek `deepseek-flash`; Gemini **`gemini-3.8-flash`** per user update relayed by root. Actual AWS call validated on 2026-11-04 at 11:21 UTC; see `docs/aws-smoke.json`.
- Qwen: pinned Qwen2.5-7B-Instruct revision, Transformers NF4 on Colab. CUDA path not yet integration-tested.
- Human data boundary: only original `Empathy` maps to requested dimensions. Custom persona/quality/safety, pairwise preferences and delayed retest remain pending. No synthetic human labels.
- Root allocation only; do not `colab new` here. Do not modify other experiments or existing server services.

## Next commands on server

Working directory `/srv/exp-runner/repos/judge-align`.

1. Run `python3 -m unittest discover -s tests -v`.
2. If ignored datasets were not copied: `python3 scripts/run.py prepare --fetch`, then `python3 scripts/run.py requests`.
3. Provider keys must already be exported from `/srv/exp-runner/secrets/providers.env` by the supervisor; never print that file or keys.
4. API smoke is complete. Do not rerun with `--max-calls 1` merely to check it: that would process the next pending request. Inspect `docs/aws-smoke.json` and existing terminal records. Resume full execution only when root authorizes handoff.
5. Inspect strict JSON parse, usage accounting, terminal success status, model version. Resume without `--max-calls` to finish remaining requests; default model is fixed in config.
6. On root-allocated L4 session upload repository **plus ignored prepared data**, install `.[qwen]`, run Qwen smoke then formal continuation. Download Qwen JSONL before releasing that session. Save `pip freeze` plus CU rate/start/stop/balance.
7. `python3 scripts/run.py report --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl`.
8. `python3 scripts/verify_completion.py` must pass only real completed automated results. Update README with actual findings and `docs/cost.md` with real usage; remain awaiting human annotation where required.

## Recovery

One writer per output JSONL. Reusing the same config and output skips successful request hashes. Do not change model/config midway and combine outputs. `started` with no terminal record indicates unknown provider billing outcome: investigate, record the finding, then explicitly retry with `--retry-unknown` if appropriate. JSONL with a torn final line fails closed; archive it and repair only the incomplete final record after checking whether the provider call completed. Three failed records stop a request. Do not fake outputs to satisfy the verifier.

Provider 401/403, quota, GPU access or missing dependencies are actual blockers. Missing human labels should not block the remaining automatic judgments; report nullable statistics and continue independent work. Automatic label substitution or changing judge provider silently is forbidden.

## Remaining scientific work

- Human labels for custom dimensions and preferences; 50 genuine delayed retests.
- Review actual judge failures and top 20 disagreements with examples.
- Formal QWK/Spearman heatmap and position/length bias conclusions.
- Runtime dependency compatibility and exact environment capture on the allocated GPU.
- Current pricing input and complete cost ledger. Undefined prices remain unknown.
