# E4 cost ledger

Initial preparation: public source downloads and local tests only; no paid API calls or GPU allocation by the E4 implementation worker.

Each `results/<provider>.jsonl` records every started/terminal request, exact model/config hash, input/output/cache/thought token counts when supplied, timestamps and provider metadata. A crash after request submission remains `started`: billing is unknown, and automatic resume refuses to repeat it. After operator review, `--retry-unknown` permits an explicit retry. Three failed recorded attempts stop that request; transient HTTP 429/5xx have up to three transport attempts.

`pricing_usd_per_million` starts at null. Fill official current per-million input/output/cache prices in a frozen configuration before formal work if dollar estimates are needed. Null pricing is reported as unknown, never zero. Provider invoices remain authoritative. Failed parse responses can still consume tokens and are included in known estimated spend. There is no artificial budget cutoff.

Root owns Colab allocation. Record each Qwen session's ID, GPU, start/stop, actual CU rate and balance here after it ends; do not start a new session from this repository. Qwen emits torch/CUDA/GPU/model revision metadata. No GPU session exists for E4 yet.

| Session | GPU | Start/end UTC | Rate CU/h | CU consumed | Status |
|---|---|---|---|---|---|
| — | — | — | — | — | Not started |

## Recorded API usage — 2026-11-04

The first recorded request from each API provider returned valid four-dimension JSON scores. Their raw records remain in `results/gemini.jsonl` and `results/deepseek.jsonl`; the formal campaign reuses them. The full API queues now run under `exp-e4-apis.service`. No GPU is allocated by this API-only unit.

| Model | End UTC | Input | Visible output | Additional thinking | Cache hit | Published-price estimate USD |
|---|---|---:|---:|---:|---:|---:|
| gemini-3.8-flash | 11:21:15 | 979 | 28 | 299 | 0 | 0.00196050 |
| deepseek-flash | 11:21:36 | 937 | 833 (includes 801 reasoning) | 0 additional | 0 | 0.00064035 |

Total published-price estimate: **$0.00260085**. Gemini paid standard rates were verified as $0.75/M input and $3.75/M output including thinking, valid through 2026-12-31; whether this account receives a free tier was not checked. DeepSeek request occurred outside published peak windows (UTC 01:00–04:00 and 06:00–10:00), using $0.15/M uncached input and $0.60/M output. These are computed list-price estimates, not an invoice. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Request pricing remains null in the execution config. Continuation deduplicates successful `(request_id, requested_model)` pairs even after output capacity changes, so it does not repeat successful calls. This post-hoc price reconciliation is separate from raw provider events. For the complete run, reconcile dynamic peak/off-peak prices by request timestamp and re-check published prices; never change model or inference settings while resuming an existing result file.

## Formal continuation change

At 2026-11-04 12:00 UTC, DeepSeek output capacity was increased from 1536 to 8192 after reasoning tokens truncated two visible JSON responses and consumed the entire output in a third. Existing complete results were retained. The new adapter preserves usage and finish reason even for empty visible content. The original empty-content attempt predates that fix and has unknown token cost; do not treat it as free. `exp-e4-deepseek.service` continues this provider while Gemini's original worker is unchanged.

## E4 Qwen allocation

A single A100 request succeeded at 2026-11-04 12:20:25 UTC: session `exp-e4-qwen`, endpoint `gpu-a100-s-ass1c0-28f4fskn9e3s6`. Full 1000-request inference uses run ID `E4-qwen-formal-001`; actual GPU and torch/CUDA versions are written to `results/qwen-run.json`, and Drive copy receipts to `results/qwen-drive-copy.json`. Record final CU balance after collection and stop.
