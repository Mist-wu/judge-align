# E4 cost ledger

Initial preparation: public source downloads and local tests only; no paid API calls or GPU allocation by the E4 implementation worker.

Each `results/<provider>.jsonl` records every started/terminal request, exact model/config hash, input/output/cache/thought token counts when supplied, timestamps and provider metadata. A crash after request submission remains `started`: billing is unknown, and automatic resume refuses to repeat it. After operator review, `--retry-unknown` permits an explicit retry. Three failed recorded attempts stop that request; transient HTTP 429/5xx have up to three transport attempts.

`pricing_usd_per_million` starts at null. Fill official current per-million input/output/cache prices in a frozen configuration before formal work if dollar estimates are needed. Null pricing is reported as unknown, never zero. Provider invoices remain authoritative. Failed parse responses can still consume tokens and are included in known estimated spend. There is no artificial budget cutoff.

Root owns Colab allocation. Record each Qwen session's ID, GPU, start/stop, actual CU rate and balance here after it ends; do not start a new session from this repository. Qwen emits torch/CUDA/GPU/model revision metadata. No GPU session exists for E4 yet.

| Session | GPU | Start/end UTC | Rate CU/h | CU consumed | Status |
|---|---|---|---|---|---|
| — | — | — | — | — | Not started |
