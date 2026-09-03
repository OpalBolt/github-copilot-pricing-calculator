# Token cost calculator

A static, three-tool site for comparing model prices. A landing hub links to
three calculators: GitHub Copilot, Cortecs, and Provider comparison. Each is a
sortable table of models with an estimated cost for a token mix you set.

Live version: [`docs/index.html`](docs/index.html) — the hub, published via GitHub
Pages.

## The tools

### GitHub Copilot calculator

Compares what every GitHub Copilot model costs in AI credits. 1 credit equals
$0.01. Enter a token mix and a budget. The table shows the estimated cost, a
relative-cost bar, and how many runs fit the budget. Pick up to five models to
compare in a bottom tray. A task guide recommends models for each kind of work.

### Cortecs calculator

Compares what Cortecs models cost in euros. The headline price is the cheapest
provider per model. Click a row to expand a nested table of its providers, each
with its price, quantization, context size, and features. Providers carry
EU-sovereign (🇪🇺) and zero-data-retention (🔒) badges. Filter chips narrow by
Sovereign-only, ZDR, Reasoning, Tools, Vision, or Audio. Add up to five models to
a compare tray.

### Provider comparison

Compares DeepSeek and z.ai side by side. Enter a budget and a token mix. The
table shows the effective tokens per dollar for every model across pay-per-token
and subscription plans. A tier selector and off-peak toggle adjust the devpack
math. Filter by provider or show all models.

## Data sources

The three tools fetch data differently.

- **GitHub Copilot** — scrapes the GitHub Copilot docs into `pricing.json` and
  `model_comparison.json`.
- **Cortecs** — one API call to `GET https://api.cortecs.ai/v1/models?extended=true&currency=EUR`.
  No key needed. No scraping.
- **Provider comparison** — scrapes DeepSeek and z.ai pricing pages into
  `providers.json`.

`fetch_cortecs.py` writes `cortecs.json`. The fetch script derives the
sovereignty and ZDR sets by diffing the API's filter responses, then bakes them
into the JSON. `fetch_providers.py` writes `providers.json`.

All data ships as static JSON baked into the HTML at build time. There is no
backend and no runtime fetch.

## Project structure

```text
fetch_pricing.py            # GitHub Copilot docs -> pricing.json
fetch_model_comparison.py   # GitHub Copilot docs -> model_comparison.json
fetch_cortecs.py            # Cortecs API -> cortecs.json
fetch_providers.py          # DeepSeek + z.ai scrapers -> providers.json
generate_html.py            # Renders the hub + all three tools
pricing.json                # GitHub Copilot pricing (checked in)
model_comparison.json       # GitHub Copilot task data (checked in)
cortecs.json                # Cortecs data (checked in)
providers.json              # Provider comparison data (checked in)
templates/                  # Jinja2 templates + shared CSS/JS for the three pages
docs/
  index.html                # The landing hub (what gets published)
  copilot.html              # GitHub Copilot calculator
  cortecs.html              # Cortecs calculator
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
Run all four through mise:

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
