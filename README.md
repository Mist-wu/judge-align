# 中文角色对话的 judge 与人工评分一致性

三类 judge 与 CharacterEval 已公开共情评分的一致性有限；本次结果不足以支持用模型评分替代人工标注。

逐条打分的 1,800 次原定请求已执行完毕，位置交换评测仍在运行；完整执行状态见 `HANDOFF.md` 和本机 `docs/formal-progress.json`。以下逐条打分结果来自真实输出，格式失败保持缺失。

| Judge | 写法 | 有效 N | 共情 QWK [95% CI] | Spearman [95% CI] |
|---|---|---:|---:|---:|
| deepseek | direct | 200 | 0.184 [0.060, 0.296] | 0.199 [0.062, 0.329] |
| deepseek | rationale | 200 | 0.250 [0.110, 0.365] | 0.262 [0.117, 0.390] |
| deepseek | anchored | 200 | 0.127 [0.006, 0.250] | 0.135 [-0.002, 0.271] |
| gemini | direct | 200 | 0.185 [0.071, 0.299] | 0.207 [0.073, 0.333] |
| gemini | rationale | 200 | 0.175 [0.074, 0.278] | 0.200 [0.067, 0.330] |
| gemini | anchored | 200 | 0.157 [0.060, 0.258] | 0.170 [0.042, 0.287] |
| qwen | direct | 198 | 0.097 [0.005, 0.187] | 0.135 [0.005, 0.260] |
| qwen | rationale | 196 | 0.140 [0.025, 0.248] | 0.185 [0.043, 0.318] |
| qwen | anchored | 199 | 0.126 [-0.011, 0.240] | 0.114 [-0.027, 0.239] |

- 九组 QWK 点估计为 **0.097–0.250**，置信区间大量重叠，不据此宣称某个 judge 优于其他模型。
- 按固定开发集选择 **qwen / anchored**；公平比较使用全部写法共同有效的 **193** 条样本。独立测试 n=157，QWK **0.125 [-0.016, 0.253]**，区间包含零。该提示只作为开发集选出的候选保存，不宣称已验证为可靠 judge。
- 原始共情标注覆盖 **200** 条；其余 **3** 个自定义维度、两两偏好及 **50** 条隔日重标仍需真实人工完成。

开发/测试按对话前缀连通组划分为 39/161 条；不能把同一对话的不同角色或不同轮次分到两边。193 条共同有效样本中实际开发/测试为 36/157。划分修正、原始格式有效率、重试与尾逗号恢复均在报告中披露；没有按结果重新调提示或修改人工原分。

所有置信区间使用 1,000 次对话组 bootstrap。公开 reward-model 训练数据可能受基座模型污染，自定义共情锚点也并非原标注说明的逐字复制，因此不应把分歧直接解释为人工或模型一方必然错误。

逐条解释见 [20 个分歧案例](docs/disagreement-analysis.md)，统计见 [正式报告](results/report.md)，开发集候选提示见 [selected-prompt.json](results/selected-prompt.json)。这些案例解释来自 Codex 分析，不是新人工标注。
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

Gemini's original worker also uses 1536. After a real pairwise reply reached `MAX_TOKENS` with 1470 thinking tokens, the continuation configuration was raised to 8192 for missing requests only. The active original worker is not restarted; successful outputs remain unchanged. Repeated malformed pairwise JSON is resumed with `configs/gemini-pairwise-continuation.json`, which adds the official `responseJsonSchema` constraint for the already-required winners/reasons fields. It is used only with pairwise request subsets, keeps the original prompts and parses the whole JSON strictly. These format-control changes remain visible in raw configuration hashes and report metadata. See [Gemini structured output](https://aistudio.google.com/docs/structured-output).

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

Outputs are `results/formal-summary.json`, `report.md`, `kappa.svg` and `disagreements.jsonl`. QWK and Spearman use exact paired samples with 1,000 conversation-group bootstrap resamples. Position bias uses both pair orientations. Length partial Spearman stays unavailable until independent human quality scores exist. Unknown/undefined values are `null` rather than fabricated zeros. Pairwise preference agreement is separate from ordinal QWK.

The report records the actual completed-request count. Automated completion still leaves `human_pending`; it does not certify the whole experiment complete. Costs and token accounting are described in `docs/cost.md`.

## Sources

- [CharacterEval repository and MIT license](https://github.com/morecry/CharacterEval/tree/c3d44a6fc1790cc8c4b2fd7c01f0c72930655e0c), [paper](https://aclanthology.org/2024.acl-long.638/)
- [MT-Bench / Chatbot Arena](https://arxiv.org/abs/2306.05685v4), [G-Eval](https://arxiv.org/abs/2303.16634v3)
- [DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/), [Gemini API](https://ai.google.dev/api/generate-content), [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
