# E4 baselines and source boundaries

Checked 2026-11-04. Formal automated judging is complete (3,000 requests executed, 2,971 analyzable outputs); final counts and statistics are recorded in `results/formal-summary.json` and `results/report.md`.

| Source | Published finding | How used here |
|---|---|---|
| [MT-Bench / Chatbot Arena](https://arxiv.org/abs/2306.05685v4) | Abstract reports GPT-4 agreement with human preferences above 80%, comparable to human-human agreement. | Context only. Different tasks, language, labels and judge models mean 80% is not an acceptance threshold for E4. |
| [G-Eval](https://arxiv.org/abs/2303.16634v3) | GPT-4 Spearman correlation 0.514 on summarization. | Motivation for rubric/reason-first prompts, not a directly comparable target on Chinese role play. |
| [CharacterEval paper](https://aclanthology.org/2024.acl-long.638/) and [source](https://github.com/morecry/CharacterEval) | Sparse annotations on original role-play metrics; repository released human reward-model training data in November 2024. | Exact released ratings retained with source row and metric. CharacterRM predictions are not human ratings. |

Pinned CharacterEval commit: `c3d44a6fc1790cc8c4b2fd7c01f0c72930655e0c`.
The actual downloaded `rm_train_data.json` contains 7,228 annotations, 4,241 unique response/context items, 12 original metrics and 678 Empathy-annotated items. Filenames ending `.jsonl` in this repository contain **JSON arrays**.

The experiment takes 200 reproducibly sampled Empathy-annotated responses. This enables a real human-alignment result for empathy without inventing labels. The other custom dimensions (persona, quality, safety) do not have equivalent released labels. Original `Consistency` means dialogue consistency; it must not be renamed persona consistency. Those custom labels remain human work.

The [upstream annotation guide](https://github.com/morecry/CharacterEval/blob/c3d44a6fc1790cc8c4b2fd7c01f0c72930655e0c/Predefined%20Annotated%20Examples%20of%20CharacterEval.pdf) defines empathy around perceiving and responding to emotion, with examples contrasting warm conversational comfort and impersonal advice. This experiment's frozen anchors are newly written, not the original annotation instructions. Agreement therefore measures alignment with the released ratings under these prompts; a mismatch alone does not prove the source annotator wrong. The guide was inspected on 2026-11-04 (330,953 bytes; SHA256 `e328142202cc25e6ff6a94bd2261751d65462915326ce6f89fe6d2a53a541ae2`). The upstream README describes 12 annotators in two groups with discussion to resolve disagreement; this is not a new single-person annotation study.

Published Qwen-7B/Baichuan-7B responses supply 200 distinct, same-context alternatives for the position-bias experiment. They have no matching released preference labels; pairwise human accuracy stays unavailable until actual labels exist. This source selection is not representative of all CharacterEval and may expose public benchmark contamination and self-preference by a Qwen judge.

## Measurement decisions

- Three pointwise prompts produce 1–5 scores. Spearman uses average ranks for ties; QWK fixes rating categories at 1..5. Degenerate statistics are `null`, not zero.
- Pairwise prompts return A/B/tie. Each pair is judged in both orders and mapped back to a canonical orientation. Report all-outcome inconsistency and decisive A/B flip rate separately. Pairwise results are not converted into fictional 1–5 scores.
- Confidence intervals use 1,000 paired bootstrap resamples at **dialogue-prefix group** level, preserving duplicate cases/orders from the same context.
- Length is Unicode character count. Partial Spearman controls independently human-rated response quality; no length-bias conclusion is emitted while quality labels are absent. This association is not causal.
- Human initial/retest QWK is descriptive reliability, not a mathematical upper bound for model agreement. Delayed retest requires a real person and cannot be completed on the first night.
- No prompt selection on the final test set is presented as an unbiased superiority claim. The comparison is exploratory; confirmation needs a separately frozen set.
- `docs/split-manifest.json` fixes 39 development and 161 test cases by dialogue-prefix group hash. It was committed after generation started but before aggregate rankings were inspected, and is not a preregistration. Exact label distributions are recorded in the manifest; no label-based stratification or outcome-based split search was used. The initial context-only split had ten cross-split prefix pairs across roles and was revised before inspecting model/prompt aggregate rankings.
