<!-- Trimmed copy of https://docs.x.ai/developers/pricing.md (fetched
2026-10-19) for parser tests: the currency statement, the text-API table
with three models, and the two non-token tables that follow it. All kept
rows are published numbers. grok-4.3's long-context row is trimmed so one
model covers the single-row (no-tier) shape. -->

#### Key Information

# Pricing

All prices are in USD. For per-model details, see the [models page](/developers/models).

### Text API Pricing

| Model | Context | Input / 1M tokens | Cached input / 1M tokens | Output / 1M tokens |
| --- | --- | --- | --- | --- |
| grok-4.7 (< 200k prompt tokens) | 500k | $2.00 | $0.50 | $6.00 |
| grok-4.7 (≥ 200k prompt tokens) | 500k | $4.00 | $1.00 | $12.00 |
| grok-4.3 (< 200k prompt tokens) | 1M | $1.25 | $0.20 | $2.50 |
| grok-build-0.1 (< 200k prompt tokens) | 256k | $1.00 | $0.20 | $2.00 |
| grok-build-0.1 (≥ 200k prompt tokens) | 256k | $2.00 | $0.40 | $4.00 |

*Prices shown per million tokens. Models listed with two rows use long context pricing: requests whose prompt reaches the listed token threshold are billed at the higher rate for all tokens in the request.*

### Imagine Pricing

| Model | Cost |
| --- | --- |
| grok-imagine-image | $0.02 / image |
| grok-imagine-video | $0.050 / sec |

### Voice Pricing

| Mode | Cost |
| --- | --- |
| Speech to Speech (grok-voice-3.0) | $0.08 / min ($4.80 / hr)<br />$0.004 / text input |
| Text to Speech | $15.00 / 1M chars |
