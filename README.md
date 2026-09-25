# Token cost calculator

A static, three-tool site for comparing model prices. A landing hub links to
three calculators: GitHub Copilot, AI routers, and provider plans. Each
calculator estimates the cost of a token mix.

Live version: [`docs/index.html`](docs/index.html) — the hub, published via GitHub
Pages.

## The tools

### GitHub Copilot calculator

Compares what every GitHub Copilot model costs in AI credits. 1 credit equals
$0.01. Enter a token mix and a budget. The table shows the estimated cost, a
relative-cost bar, and how many runs fit the budget. Pick up to five models to
compare in a bottom tray. A task guide recommends models for each kind of work.

### AI Router Price Calculator

Compares Router Prices from Cortecs, EUrouter, and OpenRouter in euros. Each row
is one router model offer. The EU routing filter uses each router's published
EU price and hides offers without one.

The calculator keeps search, sorting, capability filters, budget presets,
column controls, and a five-offer comparison tray. Price details explain the
source, named providers, currency conversion, and cached-input estimates.

### Provider comparison

Compares DeepSeek and z.ai side by side. Enter a budget and a token mix. The
table shows the effective tokens per dollar for every model across pay-per-token
and subscription plans. A tier selector and off-peak toggle adjust the devpack
math. Filter by provider or show all models.

## Data sources

The three tools fetch data differently.

- **GitHub Copilot** — scrapes the GitHub Copilot docs into `pricing.json` and
  `model_comparison.json`.
- **AI routers** — reads the public bulk model catalogs from Cortecs, EUrouter,
  and OpenRouter. It also reads the Cortecs and OpenRouter EU catalogs.
- **ECB exchange rate** — reads series `EXR.D.USD.EUR.SP00.A`. The build divides
  OpenRouter USD prices by the latest USD-per-EUR observation.
- **Provider comparison** — scrapes DeepSeek and z.ai pricing pages into
  `providers.json`.

`fetch_router_pricing.py` writes `router-pricing.json`. If one router fails,
the script can keep that router's cached data for seven days. It marks cached
data as stale. It omits the router after seven days and fails only when no
router data remains.

All data ships as static JSON baked into the HTML at build time. There is no
backend and no runtime fetch.

The router build uses these bulk endpoints:

| Data | Endpoint |
|---|---|
| Cortecs unrestricted | `https://api.cortecs.ai/v1/models?extended=true&currency=EUR` |
| Cortecs EU routing | The Cortecs endpoint above with `eu_native=true` |
| EUrouter | `https://api.eurouter.ai/api/v1/models` |
| OpenRouter unrestricted | `https://openrouter.ai/api/v1/models` |
| OpenRouter EU routing | `https://eu.openrouter.ai/api/v1/models` |
| ECB USD per EUR | `https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A` |

The build uses only EUrouter offers that publish EUR prices. It uses only
text-output chat offers from each router. A missing cached-input rate uses the
input rate as an estimate and appears with a warning in the calculator.

## Project structure

```text
fetch_pricing.py            # GitHub Copilot docs -> pricing.json
fetch_model_comparison.py   # GitHub Copilot docs -> model_comparison.json
fetch_router_pricing.py     # Router catalogs + ECB -> router-pricing.json
fetch_providers.py          # DeepSeek + z.ai scrapers -> providers.json
generate_html.py            # Renders the hub + all three tools
pricing.json                # GitHub Copilot pricing (checked in)
model_comparison.json       # GitHub Copilot task data (checked in)
router-pricing.json         # Normalized router offers (checked in)
providers.json              # Provider comparison data (checked in)
templates/                  # Jinja2 templates + shared CSS/JS for the three pages
docs/
  index.html                # The landing hub (what gets published)
  copilot.html              # GitHub Copilot calculator
  router-pricing.html       # AI Router Price Calculator
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
