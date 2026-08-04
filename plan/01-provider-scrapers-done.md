# 01 — Provider scrapers

## Blocked by

None — can start immediately.

## What to build

`fetch_providers.py` scrapes DeepSeek and z.ai pricing pages and writes a
single `providers.json`.

The script runs three scraper functions, each returning a provider object. A
`main()` merges them into the unified `providers` array and writes the JSON.

### DeepSeek scraper

Scrape `https://api-docs.deepseek.com/quick_start/pricing/`. Parse the HTML
table for two models: deepseek-v4-flash and deepseek-v4-pro. Extract input
(cache hit), input (cache miss), and output prices per 1M tokens. Context
size is 1M for both. Currency is USD. Both models get
`default_visible: true`.

### z.ai paygo scraper

Scrape `https://docs.z.ai/guides/overview/pricing.md`. Parse the markdown
table for text models only — skip vision, image, video, audio, and agent
tables. Extract input, cached input, and output prices per 1M tokens. Set
`default_visible: true` for models that also appear in the devpack
(GLM-5.2, GLM-5-Turbo, GLM-4.7). Set `default_visible: false` for the rest.

### z.ai Devpack scraper

Scrape `https://docs.z.ai/devpack/overview.md`. Extract:

- Plan tiers with monthly cost and weekly credits.
- Credit multipliers per model (input, cached, output).
- Off-peak multiplier and label.

Models get `default_visible: true`. The 5-hour credit limits are not scraped.

### Output

Write `providers.json` to the repo root. The schema follows the plan —
a `providers` array with three entries.

## Acceptance criteria

- [ ] `python fetch_providers.py` writes a valid `providers.json`.
- [ ] `providers.json` contains three provider entries (deepseek, zai, zai-devpack).
- [ ] DeepSeek entry has two models with correct prices.
- [ ] z.ai paygo entry has all text models from the pricing page.
- [ ] z.ai devpack entry has three tiers and three models with correct multipliers.
- [ ] Re-running the script overwrites `providers.json` cleanly.
