# Token cost calculator

A static, four-tool site for comparing model prices. A landing hub links to
four calculators: GitHub Copilot, EU router pricing, model pricing, and
provider plans. Each calculator estimates the cost of a token mix.

Live version: [`docs/index.html`](docs/index.html) — the hub, published via GitHub
Pages.

> [!NOTE]
> This project is 100% vibe coded. An AI agent wrote the code. A human gave
> directions, reviewed the results, and tested the site. No line was hand-written.

## The tools

### GitHub Copilot calculator

Compares what every GitHub Copilot model costs in AI credits. 1 credit equals
$0.01. Enter a token mix and a budget. The table shows the estimated cost, a
relative-cost bar, and how many runs fit the budget. Pick up to five models to
compare in a bottom tray. A task guide recommends models for each kind of work.

### EU Router Price Calculator

Compares EU routing prices from Cortecs, EUrouter, and OpenRouter in euros,
with direct Claude, DeepSeek, OpenAI, and z.ai API prices as marked baselines,
and Mistral's EU regional endpoint (api.eu.mistral.ai) as an EU-claiming
direct API whose EU prices bill at 1.1× its list prices. Router rows are
router model offers. Every row either uses the router's
published EU Router Price or carries its unrestricted price with a
no-EU-routing marker.

The calculator keeps search, sorting, capability filters, budget presets,
column controls, and a five-offer comparison tray. Price details explain the
source, named providers, currency conversion, and cached-input estimates.

### Model Price Calculator

Compares every model listing from every Seller the build can query — the
three EU routers, the OpenCode Zen gateway (models.dev prices, ADR 0003),
the first-party Claude, DeepSeek, OpenAI, and z.ai APIs, and every additional
catalog adapter registered in `sources/` (the roster grows; the page and the
source registry are the live list). One flat table in euros, sorted by
estimated cost for your token mix. The same model can appear as several
listings from different Sellers — first-party and reseller prices sit side by
side, and the page never merges or groups them.

The calculator keeps search across the full catalog, sorting, capability
filters, budget presets, column controls, and a five-listing comparison tray.
Price details name each Seller's own price source, show the native per-million
rates next to the ECB conversion, and mark stale Sellers per Seller.

### Provider comparison

Compares DeepSeek, z.ai, and OpenCode Go side by side. Enter a budget and a token mix. The
table shows the effective tokens per dollar for every model across pay-per-token
and subscription plans. A tier selector and off-peak toggle adjust the devpack
math. Filter by provider or show all models.

## Data sources

The four tools fetch data differently.

- **GitHub Copilot** — scrapes the GitHub Copilot docs into `pricing.json` and
  `model_comparison.json`.
- **EU router page** — reads the public bulk model catalogs from Cortecs, EUrouter,
  and OpenRouter. It also reads the Cortecs and OpenRouter EU
  catalogs. The same build scrapes direct Claude,
  DeepSeek, OpenAI, and z.ai API prices as non-router comparison baselines,
  and Mistral's published API prices as an EU-claiming direct API (its EU
  regional endpoint bills inference at 1.1× list price).
- **Model pricing page** — reads the same catalogs plus OpenCode Zen's catalog
  with models.dev metadata (ADR 0003), the direct Claude, DeepSeek, OpenAI,
  and z.ai API prices, and every further keyless catalog adapter in the
  `sources/` registry. One Model Listing per catalog row per Seller; where a
  Seller re-lists the same model through several upstream routes at identical
  prices, the build keeps one row (the surviving variants differ in price or
  product, e.g. TEE or discounted routes).
- **ECB exchange rate** — reads series `EXR.D.USD.EUR.SP00.A`. The build divides
  USD prices by the latest USD-per-EUR observation.
- **Provider comparison** — scrapes DeepSeek, z.ai, and OpenCode Go pricing pages into
  `providers.json`.

`fetch_router_pricing.py` writes `eu-router-pricing.json`. If one router fails,
the script can keep that router's cached data for seven days. It marks cached
data as stale. It omits the router after seven days and fails only when no
router data remains. `fetch_model_pricing.py` writes `model-pricing.json` the
same way for the global page's Sellers, with one ECB rate fetch shared by the
build.

All data ships as static JSON baked into the HTML at build time. There is no
backend and no runtime fetch.

The router build uses these sources:

| Data | Endpoint |
|---|---|
| Cortecs unrestricted | `https://api.cortecs.ai/v1/models?extended=true&currency=EUR` |
| Cortecs EU routing | The Cortecs endpoint above with `eu_native=true` |
| EUrouter | `https://api.eurouter.ai/api/v1/models` |
| OpenRouter unrestricted | `https://openrouter.ai/api/v1/models` |
| OpenRouter EU routing | `https://eu.openrouter.ai/api/v1/models` |
| OpenCode Zen catalog | `https://opencode.ai/zen/v1/models` |
| OpenCode Zen prices (ADR 0003) | `https://models.dev/api.json` (OpenCode Zen entry) |
| DeepInfra catalog | `https://api.deepinfra.com/v1/models` |
| Novita catalog | `https://api.novita.ai/v3/openai/models` |
| Requesty catalog | `https://router.requesty.ai/v1/models` |
| nano-gpt catalog | `https://nano-gpt.com/api/v1/models?detailed=true` |
| Vercel AI Gateway catalog | `https://ai-gateway.vercel.sh/v1/models` |
| Kilo catalog | `https://api.kilo.ai/api/gateway/models` |
| Chutes catalog | `https://llm.chutes.ai/v1/models` |
| LLM Gateway catalog | `https://api.llmgateway.io/v1/models` |
| aiand catalog | `https://api.aiand.com/v1/models` |
| AI/ML API catalog | `https://api.aimlapi.com/v1/models?include=pricing,modalities` |
| Ambient catalog | `https://api.ambient.xyz/v1/models` |
| Crossmodel catalog | `https://www.crossmodel.ai/api/models` |
| Eden AI catalog | `https://api.edenai.run/v3/models` |
| Empirio Labs catalog | `https://api.empiriolabs.ai/v1/models` |
| Engy catalog | `https://api.engy.ai/v1/models` |
| FriendliAI catalog | `https://api.friendli.ai/serverless/v1/models` |
| Hyper catalog | `https://hyper.charm.land/v1/models` |
| Inceptron catalog | `https://api.inceptron.io/v1/models` |
| NEAR AI catalog | `https://cloud-api.near.ai/v1/models` |
| OfoxAI catalog | `https://api.ofox.ai/v2/models/catalog?include=provider_price&limit=500` |
| Pioneer (Fastino) catalog | `https://api.fastino.ai/v1/models` |
| Prime catalog | `https://api.pinference.ai/api/v1/models` |
| Tinfoil catalog | `https://inference.tinfoil.sh/v1/models` |
| Venice catalog | `https://api.venice.ai/api/v1/models?type=text` |
| Claude model catalog | `https://platform.claude.com/docs/en/api/http/beta/models/list.md` |
| Claude direct API pricing | `https://platform.claude.com/docs/en/about-claude/pricing.md` |
| DeepSeek direct API | `https://api-docs.deepseek.com/quick_start/pricing/` |
| OpenAI model catalog | `https://developers.openai.com/api/reference/resources/models/methods/list` |
| OpenAI direct API pricing | `https://developers.openai.com/api/docs/pricing.md` |
| z.ai direct API | `https://docs.z.ai/guides/overview/pricing.md` |
| xAI direct API pricing | `https://docs.x.ai/developers/pricing.md` |
| Mistral direct API pricing | `https://docs.mistral.ai/inference/pricing.md` |
| Meta direct API pricing | `https://dev.meta.ai/docs/pricing-rate-limits.md` |
| OpenRouter usage ranking (default view) | `https://openrouter.ai/api/v1/datasets/rankings-daily` — keyed: `Authorization: Bearer $OPENROUTER_DATASETS_KEY` |
| ECB USD per EUR | `https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A` |

The model-pricing build fetches the default view's usage ranking from the
rankings-daily dataset with the build's only secret,
`OPENROUTER_DATASETS_KEY`. Without the key, or if the fetch fails, the build
reuses the previous selection (stale-marked, dropped after seven days) and
then the committed `fixtures/openrouter-rankings.json` snapshot — a keyless
build never fails.

The build uses EUrouter offers that publish EUR or USD prices. It converts USD
prices with the same ECB rate as OpenRouter. It uses only text-output chat
offers from each router. A missing cached-input rate uses the input rate as an
estimate and appears with a warning in the calculator.

## Project structure

```text
fetch_pricing.py            # GitHub Copilot docs -> pricing.json
fetch_model_comparison.py   # GitHub Copilot docs -> model_comparison.json
fetch_router_pricing.py     # Router catalogs + ECB -> eu-router-pricing.json
fetch_model_pricing.py      # All Sellers' catalogs + ECB -> model-pricing.json
default_view.py             # Usage-ranked opening selection for the Model Price Calculator
fetch_providers.py          # DeepSeek + z.ai scrapers -> providers.json
changelog.py                # Diffs fetched data vs git HEAD -> changelog.json
generate_html.py            # Renders the hub + all four tools
pricing.json                # GitHub Copilot pricing (checked in)
model_comparison.json       # GitHub Copilot task data (checked in)
eu-router-pricing.json      # Normalized EU router offers (checked in)
model-pricing.json          # Normalized model listings per Seller (checked in)
providers.json              # Provider comparison data (checked in)
changelog.json              # Per-category change log rendered into each page (checked in)
fixtures/                   # Committed catalog samples and rankings snapshot (checked in)
sources/                    # Seller listings adapters + the shared source registry
templates/                  # Jinja2 templates + shared CSS/JS for the pages
docs/
  index.html                # The landing hub (what gets published)
  copilot.html              # GitHub Copilot calculator
  eu-router-pricing.html    # EU Router Price Calculator
  model-pricing.html        # Model Price Calculator
  cortecs.html              # Compatibility redirect
  provider-compare.html     # Provider comparison
mise.toml                   # Tool versions and project tasks
requirements.txt            # Python dependencies
```

## Building

The repo uses [mise](https://mise.jdx.dev/) to install Python, create `.venv`,
install dependencies, and run project tasks.

```bash
mise install
mise run build          # refresh all data sources and render the site
mise run build-cached   # render the site from the checked-in JSON files
```

Run the generated site at `http://localhost:8080`:

```bash
mise run serve
```

List all available tasks:

```bash
mise tasks
```

## Updating data

The fetch scripts are safe to re-run. Each script writes only its own JSON file.
Run all four data jobs through mise:

```bash
mise run fetch
```

Then render the site with `mise run build-cached`. `mise run build` combines
both steps.

## Checks

Check the Python code with Ruff:

```bash
mise run lint
```
