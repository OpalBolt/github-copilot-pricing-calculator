# Provider price comparison

## Core idea

A price-comparison tool that puts model providers side by side. Providers
have different pricing models — pay-per-token, subscription credits, or
whatever comes next — so the page normalizes everything to one number:
**effective tokens per dollar** at the user's own token mix.

The first two providers are **DeepSeek** (paygo) and **z.ai** (paygo +
Devpack subscription). The data model is designed so adding a third provider
is a new entry in an array, not a code change.

The tool is a new page in the existing token-calculator repo, linked from the
landing hub.

## Problem it solves

Comparing providers today means opening multiple pricing pages and doing
mental math across incompatible pricing models. This tool puts every provider
in one table and answers: *"I have $X. What does that get me on each?"*

## Decisions (locked during the jam)

| Area | Decision |
|---|---|
| Purpose | Provider price comparison — "what does $X buy me?" |
| Data model | A single `providers` array. Each entry has a `pricing_type` (`paygo` or `subscription`), a list of models, and provider-specific fields (tiers for subscriptions). Adding a provider = append to the array. |
| Default visible models | Each model carries a `default_visible: true/false` flag. A "Show all models" chip reveals the rest. Providers set this flag in their scraper (e.g. DeepSeek marks both models visible; z.ai marks only devpack-eligible models visible). |
| Core metric | **Effective tokens per dollar** — given a budget and token mix, how many tokens can you get? |
| Controls | Same token-mix + budget panel as the Copilot/Cortecs tools, in USD. Subscription-tier selector and off-peak checkbox appear when any subscription provider is present. |
| Subscription math | Credits = (input × mult_input + cached × mult_cached + output × mult_output) / 10,000. Effective $/1M derived from: monthly cost → weekly cost, credits/week → tokens/week at the user's mix. |
| Off-peak | z.ai devpack charges 50% credits during off-peak (Mon–Fri 14:00–18:00 UTC+8). A checkbox toggles off-peak; defaults to peak. The off-peak multiplier is a field on the subscription provider entry, so other providers can set their own. |
| Cache-hit ratio | User-adjustable via the token mix inputs (cached input %). No hardcoded default — the user sets it. |
| Free models | Models with all-zero pricing show "Free" in the Effective tokens/$ column, skip math. |
| Currency | USD (both initial providers price in USD). Currency is a field on each provider entry for future multi-currency support. |

## Data source

Each provider publishes pricing as a static page — no APIs, HTML or markdown
scraping. One fetch script per provider, all writing into a shared
`providers.json`.

### DeepSeek (paygo)

`https://api-docs.deepseek.com/quick_start/pricing/` — Docusaurus site,
pricing in an HTML `<table>`. Two models (v4-flash, v4-pro) with input (cache
hit), input (cache miss), and output prices. Context: 1M for both.

### z.ai paygo

`https://docs.z.ai/guides/overview/pricing.md` — raw markdown. 14 text
models, plus vision/image/video/audio/agent tables. We only scrape the text
models table.

### z.ai Devpack (subscription)

`https://docs.z.ai/devpack/overview.md` — raw markdown. Contains:

- Plan tiers: Lite (10K credits/week, $18/mo), Pro (60K credits/week,
  $80/mo), Max (140K credits/week, $168/mo).
- Credit multipliers per model: GLM-5.2 (6.9/1.7/24), GLM-5-Turbo
  (5.7/1.5/21), GLM-4.7 (4.6/1.2/16), GLM-4.6V (1.2/0.3/2.7).
- 5-hour credits in addition to weekly (2K/12K/28K) — ignore for v1, weekly
  is the binding constraint.
  `# ponytail: 5hr limit is burst protection, weekly is the real cap`

### Unified JSON shape

All scrapers write into one `providers.json` (checked in):

```json
{
  "providers": [
    {
      "id": "deepseek",
      "name": "DeepSeek",
      "pricing_type": "paygo",
      "currency": "USD",
      "models": [
        { "id": "deepseek-v4-flash", "input": 0.14, "input_cache": 0.0028, "output": 0.28, "context": 1048576, "default_visible": true },
        { "id": "deepseek-v4-pro", "input": 0.435, "input_cache": 0.003625, "output": 0.87, "context": 1048576, "default_visible": true }
      ]
    },
    {
      "id": "zai",
      "name": "z.ai",
      "pricing_type": "paygo",
      "currency": "USD",
      "models": [
        { "id": "glm-5.2", "input": 1.4, "input_cache": 0.26, "output": 4.4, "default_visible": true },
        { "id": "glm-4.7-flashx", "input": 0.07, "input_cache": 0.01, "output": 0.4, "default_visible": false },
        "..."
      ]
    },
    {
      "id": "zai-devpack",
      "name": "z.ai Devpack",
      "pricing_type": "subscription",
      "currency": "USD",
      "off_peak_multiplier": 0.5,
      "off_peak_label": "Mon–Fri 14:00–18:00 UTC+8",
      "tiers": [
        { "name": "Lite", "monthly_usd": 18, "weekly_credits": 10000 },
        { "name": "Pro", "monthly_usd": 80, "weekly_credits": 60000 },
        { "name": "Max", "monthly_usd": 168, "weekly_credits": 140000 }
      ],
      "models": [
        { "id": "glm-5.2", "mult_input": 6.9, "mult_cached": 1.7, "mult_output": 24, "default_visible": true },
        { "id": "glm-5-turbo", "mult_input": 5.7, "mult_cached": 1.5, "mult_output": 21, "default_visible": true },
        { "id": "glm-4.7", "mult_input": 4.6, "mult_cached": 1.2, "mult_output": 16, "default_visible": true }
      ]
    }
  ]
}
```

**Adding a provider** (e.g. Qwen) means:

1. Write a scraper function in `fetch_providers.py`.
2. Append its output to the `providers` array.
3. Done. The UI iterates the array — no template changes needed.

## Architecture

Same repo, same fetch → JSON → Jinja2 → static HTML pipeline. New/changed
files:

```
fetch_providers.py             # NEW — runs all provider scrapers → providers.json
providers.json                 # NEW — cached provider data (checked in)
generate_html.py               # extended — also render docs/provider-compare.html
templates/
  landing.html.j2              # extended — new card on the hub
  provider-compare.html.j2     # NEW — provider comparison page
  macros.html.j2               # extended with provider badge macros
  styles.css.j2                # extended with provider comparison styles
  provider-compare.app.js.j2   # NEW — budget, token mix, effective math, filters
docs/
  index.html                   # landing (updated)
  provider-compare.html        # NEW — provider comparison output
```

Notes:

- One fetch script, one JSON file. Each provider is a function in
  `fetch_providers.py` that returns a provider object; main() merges them.
  Adding a provider = write a function + add it to the list.
- UI iterates `providers` array. Rows, lanes, and filter chips are generated
  dynamically. No provider-specific markup.
- Subscription controls (tier selector, off-peak toggle) appear when
  `providers` contains any entry with `pricing_type: "subscription"`. Labels
  come from the data (`off_peak_label`).
- `# ponytail: per-tool JS, extract shared helpers if they spread`

## UI

A single table. Rows are provider × plan × model combinations. The key column
is **Effective tokens/$**.

Columns:

`Provider | Plan | Model | Input $/1M | Cached $/1M | Output $/1M | Effective tokens/$`

- **Provider**: provider name badge (from `provider.name`).
- **Plan**: "Paygo" for paygo providers, tier name for subscription providers
  (Lite/Pro/Max).
- **Model**: model id.
- **$/1M columns**: raw prices as published. For subscription providers, show
  the effective $/1M derived from the credit math.
- **Effective tokens/$**: budget ÷ effective blended price at the user's token
  mix.

**Controls panel:**

- **Budget** + **Token mix** (Input/Cached/Output %) — carried over from
  existing tools, in USD.
- **Subscription tier**: Lite / Pro / Max radio (default: Lite). Only shown
  when a subscription provider is present. Affects all subscription rows.
  `# ponytail: single global tier selector; if multiple subscription providers diverge in tiers, make it per-provider`
- **Off-peak toggle**: checkbox, off by default. Only shown when a
  subscription provider is present. Uses `off_peak_multiplier` from the data.
- **Show all models**: chip toggle. Default off — shows only models with
  `default_visible: true`.

Sortable columns, filter chips (search by model name), responsive table.

## Effective token math (all client-side JS)

**Paygo:**

```
blended_price = input_pct × input_price + cached_pct × cached_price + output_pct × output_price
tokens_per_dollar = 1_000_000 / blended_price
total_tokens = budget × tokens_per_dollar
```

**Subscription:**

```
weekly_cost = monthly_cost / 4.33
weighted_mult = input_pct × mult_input + cached_pct × mult_cached + output_pct × mult_output
credits_per_1M_tokens = weighted_mult × 1_000_000 / 10_000
tokens_per_week = weekly_credits / credits_per_1M_tokens × 1_000_000
effective_price_per_1M = weekly_cost / (tokens_per_week / 1_000_000)
tokens_per_dollar = 1_000_000 / effective_price_per_1M
```

When off-peak is checked, `credits_per_1M_tokens` is multiplied by the
provider's `off_peak_multiplier`.

## Edge cases

- **Free models** (all prices zero): show "Free" in the Effective tokens/$
  column, skip math.
- **Divide-by-zero**: token mix must sum to 100% with at least one slot >0%.
  Guard against all-zero.
- **Subscription tiers with different models**: currently all z.ai devpack
  tiers support the same models. If tiers diverge, the tier selector filters
  which models appear in subscription rows.
- **Multiple subscription providers**: if a second subscription provider is
  added and its tiers differ from z.ai's, the global tier selector gets
  replaced with per-provider selectors.
- **Scraping fragility**: pricing pages are static docs that change
  infrequently. Fetch runs offline during `generate_html.py`. If scraping
  breaks, cached JSON serves stale data.
  `# ponytail: no runtime fetch, no API dependency`

## Build & run

Use the mise tasks:

```bash
mise run build        # fetch all data sources, render landing + all tools
mise run build-cached # regenerate HTML from cached JSON (template iteration)
```

`fetch_providers.py` is standalone and safe to re-run (writes only
`providers.json`).

## Implementation slices

1. `01-provider-scrapers.md` — `fetch_providers.py` with DeepSeek and z.ai
   scrapers, writes `providers.json`. No blockers.
2. `02-provider-table.md` — static table from the `providers` array, all
   lanes generated dynamically. Blocked by 01.
3. `03-budget-token-mix.md` — budget + token mix inputs + effective
   tokens/$ column. Blocked by 02.
4. `04-subscription-math.md` — tier selector, credit math, off-peak toggle,
   effective price derivation. Blocked by 02.
5. `05-provider-filters.md` — "Show all models" toggle, model search, column
   sort. Blocked by 02.
6. `06-landing-card.md` — add provider comparison card to the landing hub.
   Blocked by 02.
7. `07-readme.md` — update README for the three-tool site. Blocked by 02.
