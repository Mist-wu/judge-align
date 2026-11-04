# Judge alignment on Chinese role-play responses

Compare DeepSeek, Gemini and Qwen judges with actual human labels, preserving missing-label boundaries and positional controls.

| Verified preparation | Count |
|---|---:|
| Sampled real Empathy-labelled responses | 200 |
| Distinct same-context candidate pairs | 200 |
| Planned judge requests, including both pair orders | 3,000 |

**Formal metrics are pending; these counts are preparation results, not evidence of judge quality.** Formal Gemini 3.8-flash scoring is running under `exp-e4-apis.service`; DeepSeek flash continues under `exp-e4-deepseek.service`. Existing successful records are reused. Other custom dimensions need human labels. API judges run on the server; Qwen runs only on an allocated CUDA Colab runtime, independent of the Mac.

## Prepare the full experiment

Python 3.11+ suffices; the API and analysis paths have no third-party dependencies.

```bash
python3 scripts/run.py prepare --fetch
python3 scripts/run.py requests
python3 scripts/run.py annotations
python3 scripts/run.py annotations --round retest --output data/retest-template.jsonl
```

The source is pinned and downloaded under ignored `data/raw/`; source hashes are in `docs/data-source-manifest.json`. Re-running preparation is deterministic. The generated primary cases, alternatives, pairs, prompts and annotation templates remain outside Git. See `docs/baselines.md` for the real source schema and limitations.

## Run API judges

Supply `DEEPSEEK_API_KEY` and `GEMINI_API_KEY` through the environment, never CLI arguments or tracked files. Frozen defaults are `deepseek-flash` and `gemini-3.8-flash`; change `configs/main.json` only before a new run. These are independent from the Codex subscription used by the coding agent. API default URLs use official services. `model_env` is a fallback when `model` is removed from the provider configuration.

```bash
# Run the full queues, reusing all successful records.
python3 scripts/run.py run --provider deepseek --output results/deepseek.jsonl
python3 scripts/run.py run --provider gemini --output results/gemini.jsonl
```

There are 600 pointwise and 400 paired-orientation requests per provider. Three pointwise styles are direct, concise rationale before score, and fixed rubric anchors. The fourth style is pairwise preference. All styles evaluate four dimensions in one request. No judge reads human ratings.

DeepSeek output capacity is 8192 tokens; the first formal responses used 1536, which truncated reasoning-heavy replies. Complete earlier results are retained and failed requests are retried. Reports disclose the observed configuration hashes.

The runner uses an exclusive output-file lock. A request is durably recorded before submission, and successful `(request_id, requested_model)` pairs are skipped after restart, including after output-capacity adjustment. Each raw result retains its provider configuration hash. An interrupted request with unknown billing outcome requires investigation before explicitly adding `--retry-unknown`. Provider/auth/network errors stop this provider rather than spending across the remaining queue; malformed replies are recorded and fail the command. At most three recorded failed attempts per request.

## Qwen on an already allocated Colab GPU

Do not run this on the 2 GB Lightsail host. Root owns session allocation and cleanup.

```bash
python -m pip install -e '.[qwen]'
python scripts/run.py run --provider qwen --output results/qwen.jsonl
```

`Qwen/Qwen2.5-7B-Instruct` is pinned to commit `a09a35458c702b33eeacc393d103063234e8bc28`, uses NF4 4-bit loading and BF16 compute on L4/A100. This differs from the original document's MLX quantization backend and is recorded explicitly. It rejects overlength inputs instead of silently truncating; Installed dependency versions were checked on PyPI. Run the full Qwen queue on the allocated GPU and record its actual runtime environment.

## Human labels and report

Fill the blinded `data/human-template.jsonl` using `docs/rubric.md`; the four custom dimensions must be complete. Do not ask a model to supply human labels. Same-context pair preferences and delayed human retest remain separate genuine human work. Validate completed files before use:

```bash
python3 scripts/run.py annotations --validate data/human-initial.jsonl
python3 scripts/run.py report --judgments results/deepseek.jsonl results/gemini.jsonl results/qwen.jsonl
# Add --human data/human-combined.jsonl only after genuine initial/retest annotation.
python3 scripts/reconcile_cost.py
```

Outputs are `results/formal-summary.json`, `report.md`, `kappa.svg` and `disagreements.jsonl`. QWK and Spearman use exact paired samples with 1,000 context-cluster bootstrap resamples. Position bias uses both pair orientations. Length partial Spearman stays unavailable until independent human quality scores exist. Unknown/undefined values are `null` rather than fabricated zeros. Pairwise preference agreement is separate from ordinal QWK.

The report records the actual completed-request count. Automated completion still leaves `human_pending`; it does not certify the whole experiment complete. Costs and token accounting are described in `docs/cost.md`.

## Sources

- [CharacterEval repository and MIT license](https://github.com/morecry/CharacterEval/tree/c3d44a6fc1790cc8c4b2fd7c01f0c72930655e0c), [paper](https://aclanthology.org/2024.acl-long.638/)
- [MT-Bench / Chatbot Arena](https://arxiv.org/abs/2306.05685v4), [G-Eval](https://arxiv.org/abs/2303.16634v3)
- [DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/), [Gemini API](https://ai.google.dev/api/generate-content), [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
