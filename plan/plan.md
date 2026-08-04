# Cortecs price calculator (sister site)

## Core idea

A second price-comparison tool that mirrors the GitHub Copilot token calculator,
but targets **Cortecs** models. Cortecs publishes a clean JSON API, so the data
fetch is a single request instead of HTML scraping. The new wrinkle: every model
can be served by several **providers**, each with its own price, quantization,
context size, and features. The UI has to handle that.

A small **landing page** lets a visitor pick the GitHub tool or the Cortecs tool.

## Problem it solves

Finding the price of a Cortecs model today means clicking back and forth between
models and providers. This puts every model and provider in one sortable,
filterable, budget-aware table — the same job the Copilot calculator does, in €
instead of AI credits.

## Decisions (locked during the jam)

| Area | Decision |
|---|---|
| Purpose | Price calculator in the spirit of the Copilot tool, geared to Cortecs |
| Entry point | Landing `index.html` that links to the GitHub tool and the Cortecs tool |
| Headline price | **Cheapest** provider per model (the API already returns this) + a "N providers" badge |
| Routing | One-line footnote: *prices are the cheapest available; Cortecs also offers fastest/balanced routing* (the API exposes no speed data, so cheapest is the only knowable headline) |
| Provider drill-down | **Expandable inline row** — click a model to reveal a nested table of its providers |
| Compare | A **"+"** on each model adds it to a compare tray (up to ~5), comparing models at cheapest price |
| Sovereignty / ZDR | **Filter chips** + per-provider **badges**, derived once at fetch (see below) |
| Capabilities | **Filter chips** (reasoning, tools, vision, audio) + small model badges |
| Budget calc | The token-mix → est. cost / relative bar / runs machinery carries over, in € |
 Quant honesty | Badge the cheapest provider's quantization on the row **only when `fp4`/`int4`** (the heavy compressions that explain a low price); quiet for full-quality quants. Full detail in the drill-down

## Data source

Cortecs Models API — no key needed for the public list.

```
GET https://api.cortecs.ai/v1/models?extended=true&currency=EUR
```

- `extended=true` includes `providers_details` (per-provider price, quantization,
  context size, features) — this is the field that makes the drill-down possible.
- `currency=EUR` (default). The API accepts any ISO code; EUR-only for v1, a
  currency toggle is a cheap later add.
- Top-level `pricing` on each model is **already the cheapest provider's price**.

Shape (105 models, 15 providers) — one example:

```json
{
  "id": "kimi-k3",
  "owned_by": "Moonshot AI",
  "description": "...",
  "pricing": { "currency": "EUR", "input_token": 2.693, "output_token": 13.464 },  // = cheapest
  "providers": ["nebius", "tensorix", "berget"],
  "context_size": 1048576,
  "input_modalities": ["text", "image"],
  "supported_features": ["json_mode", "reasoning", "tools"],
  "tags": ["Instruct", "Code", "Tools", "Reasoning", "Image"],
  "providers_details": {
    "nebius":  { "pricing": {...}, "quantization": "fp4", "context_size": 1024000, "supported_features": [...] },
    "tensorix":{ "pricing": {..., "cache_read_cost": 0.673}, "quantization": "fp4", "context_size": 1048576, ... },
    "berget":  { "pricing": {...}, "quantization": "int4", "context_size": 1000000, ... }
  }
}
```

Available axes from the data:
- **Capabilities**: `input_modalities` (text/image/audio), `supported_features`
  (`json_mode`, `reasoning`, `tools`), `tags` (Code, Reasoning, Image, Audio, Tools, Safety-guard).
- **Pricing**: `input_token`, `output_token`, `cache_read_cost` (53/105 models),
  plus `audio_cost`/`speech_cost` on a few voice models.
- **Per provider**: price, `quantization` (fp4/fp8/fp16/bf16/int4), `context_size`, features.
- **Context size**: ranges 22K → 1.05M, and varies by provider.

## Sovereignty & ZDR (derived, not a separate endpoint)

There is no `/providers` endpoint, but the filter params let us derive a static
provider-attribute table at fetch time. Diffing the API responses:

| Set | Providers |
|---|---|
| All (15) | aki, amazon_ireland, amazon_paris, azure_sc, azure_spc, berget, google, inceptron, infercom, ionos, mistral, nebius, ovh, scaleway, tensorix |
| EU-sovereign (`eu_native`) | aki, berget, inceptron, infercom, ionos, mistral, nebius, ovh, scaleway, tensorix |
| Not EU-sovereign | amazon_ireland, amazon_paris, azure_sc, azure_spc, google (US hyperscalers) |
| Zero-data-retention (`zdr`) | all except azure_sc, azure_spc |

`fetch_cortecs.py` records these three calls' results into a small
`providers` table baked into the JSON. Each provider in a drill-down then carries
🇪🇺 (EU-sovereign) and/or 🔒 (ZDR) badges. A "Sovereign-only" chip filters the table.

## Architecture

Same repo, restructured. Reuse the existing fetch → JSON → Jinja2 → static HTML
pipeline. New/changed files:

```
fetch_cortecs.py            # NEW — one curl to /v1/models?extended=true; derive provider table; write cortecs.json
cortecs.json                # NEW — cached Cortecs data (checked in)
generate_html.py            # extended — also render docs/cortecs.html and the landing docs/index.html
pricing.json / model_comparison.json   # unchanged (GitHub tool data)
templates/
  landing.html.j2           # NEW — switcher hub (two links + short blurb each)
  cortecs.html.j2           # NEW — Cortecs tool page structure
  page.html.j2              # GitHub tool page (unchanged)
  macros.html.j2            # extended with provider-row / badge macros
  styles.css.j2             # shared base + provider/drill-down/landing styles
  cortecs.app.js.j2         # NEW — Cortecs client JS (filters, sort, expand, +/compare, budget)
  app.js.j2                 # GitHub tool JS (unchanged)
docs/
  index.html                # NEW landing (was the GitHub tool)
  cortecs.html              # NEW — Cortecs tool output
  copilot.html              # GitHub tool output (moved from index.html)
```

Notes:
- `page.html.j2` stays the GitHub tool; the Cortecs page gets its own template
  because the provider drill-down + "+" column are new markup.
- Separate JS per tool. Shared helpers (filter/sort/bar) can be pulled out if
  duplication grows — not yet. `# ponytail: per-tool JS, extract shared if it spreads`
- Existing deep links to the old `index.html` break. Fine for this project; the
  landing page replaces it. `# ponytail: no redirects, personal project`

### Landing page

Hub `index.html` with two cards (GitHub calculator + Cortecs calculator). Locked:
this lets the GitHub calculator live as just another linked tool rather than a
headline feature, so the page never has to advertise "we compare other tools."
The lighter nav-link alternative is dropped.

## UI (Cortecs tool)

Table, one row per model, columns adapted from the Copilot tool:

`+ | Model | Owner | Capabilities | Context | Input €/1M | Cached €/1M | Output €/1M | Est. cost | Runs | Providers`

- **+** adds to the compare tray (up to ~5). Models compare at cheapest price.
- **Providers** cell: the "N providers" badge; click the row to expand.
- **Expand (drill-down)**: a nested table under the row, one line per provider —
  provider name + 🇪🇺/🔒 badges, quantization, context size, input/cached/output,
  supported features.
- **Quant badge**: a muted `fp4`/`int4` chip on the row when the cheapest provider is heavily quantized (see Edge cases).
- **Capabilities** badges on the model row (reasoning/tools/vision/audio).
- **Controls panel** (carried over): Total tokens, Input/Cached/Output %, € budget.
  Drives Est. cost and Runs columns.
- **Filter chips**: Sovereign-only, ZDR, Reasoning, Tools, Vision, Audio, plus
  free-text search by model/owner. Keep the show/hide toggles for Input/Cached/Output.
- **Relative-cost bar**: scaled to the cheapest model in the current view, as today.

## Edge cases / open questions

- **Free (€0.00) models** exist (min input price is 0.0). Guard the budget/runs
  math against divide-by-zero; show "free" instead of a bar.
- **Audio models** carry `audio_cost` (per second) and `speech_cost` (per 1M chars),
  which don't fit a €/1M-tokens column. Show token prices in the table; surface
  audio costs only in the drill-down.
- **Quantization honesty (locked)**: badge the cheapest-provider quantization on
  the row **only when `fp4` or `int4`** (the heavy compressions that explain a low
  price). Stay quiet for `fp16`/`bf16`/`fp8`. Full detail still in the drill-down.
  `# ponytail: badge only aggressive quants, avoid row noise`
- **`model_series`** groups variants (e.g. claude-opus4-7/8). One row per model id
  for v1; series grouping can come later.
- **Currency toggle**: API supports `currency=`. EUR-only for v1.
- **Compare granularity**: tray compares models at cheapest. Per-(model+provider)
  compare is a future enhancement if you want to pit specific providers.

## Build & run

Same Nix flake; the existing commands extend naturally:

```bash
nix develop
python generate_html.py            # fetch both data sources, render landing + both tools
python generate_html.py --no-fetch # regenerate HTML from cached JSON (template iteration)
```

`fetch_cortecs.py` is standalone and safe to re-run (writes only `cortecs.json`),
mirroring the existing fetch scripts.

## Implementation slices

The work breaks into seven vertical slices, each a file in this folder. Build them in dependency order.

1. `01-cortecs-model-table.md` — fetch the API and render the model table. No blockers.
2. `02-landing-hub.md` — landing hub and tool relocation. Blocked by 01.
3. `03-budget-columns.md` — budget and cost columns in euros. Blocked by 01.
4. `04-provider-drilldown.md` — provider drill-down and sovereignty badges. Blocked by 01.
5. `05-filters-badges.md` — filters, search, and row badges. Blocked by 04.
6. `06-compare-tray.md` — compare tray. Blocked by 01.
7. `07-readme.md` — README for the two-tool site. Blocked by 02.
