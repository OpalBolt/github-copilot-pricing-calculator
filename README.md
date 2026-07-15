# GitHub Copilot · Token cost calculator

A static, single-page tool for comparing what every GitHub Copilot model costs in AI
credits, exploring which model fits which task, and estimating how far a $ budget goes
per model.

Live version: [`docs/index.html`](docs/index.html) (published via GitHub Pages).

## What it does

- **Pricing & Compare** — a sortable, filterable table of every Copilot model with
  input / cached / output rates per 1M tokens, an estimated cost for a configurable
  token mix, and a relative-cost bar. Pick up to 5 models to compare side-by-side in a
  bottom tray.
- **Budget-aware Runs / Tokens columns** — enter a $ budget (default $80) and the table
  shows how many runs of your configured token mix you can afford per model, and how
  many total tokens that equals — using the same filters, search, and sort as the rest
  of the table.
- **Task Guide** — a per-task-area guide (e.g. "Deep reasoning and debugging", "Fast
  help with simple or repetitive tasks") recommending which models excel at which kind
  of work, sourced from GitHub's model comparison docs.

All data ships as static JSON (`pricing.json`, `model_comparison.json`) baked into the
generated HTML at build time — there is no backend or client-side fetching at runtime.

## Project structure

```
fetch_pricing.py            # Scrapes GitHub's models-and-pricing docs -> pricing.json
fetch_model_comparison.py   # Scrapes GitHub's model-comparison docs -> model_comparison.json
generate_html.py            # Renders templates/*.j2 + the two JSON files -> docs/index.html
pricing.json                 # Cached pricing data (checked in, refreshed by fetch script)
model_comparison.json        # Cached task/model comparison data (checked in)
templates/
  page.html.j2               # Page structure (Jinja2)
  macros.html.j2              # Reusable Jinja2 macros (inputs, filter chips, badges, cards)
  styles.css.j2                # All CSS, inlined into <head>
  app.js.j2                    # All client-side JS, inlined at the end of <body>
docs/index.html               # Generated static output — this is what gets served/published
flake.nix                     # Nix dev shell + build/serve/fetch commands
```

## Building

This repo uses a Nix flake to pin Python + Jinja2 so the build is reproducible without a
manual `pip install`.

```bash
# Enter a dev shell with Python + jinja2 + ruff available
nix develop

# Fetch the latest pricing/model-comparison data AND regenerate docs/index.html
python generate_html.py

# Regenerate docs/index.html from the existing pricing.json / model_comparison.json
# (skip the network fetch — useful when iterating on templates)
python generate_html.py --no-fetch
```

Or, without entering a dev shell:

```bash
nix run .#build -- --no-fetch   # fetch + generate, or pass --no-fetch to skip fetching
nix run .#fetch                 # fetch pricing.json only
nix run .#serve                 # serve the repo root at http://localhost:8080
```

## How pricing works

- 1 AI credit = $0.01 USD.
- Est. cost for a model = `(input tokens × input rate + cached tokens × cached rate +
  output tokens × output rate) ÷ 1,000,000`, based on the token mix (Total tokens,
  Input %, Cached %, Output %) configured in the controls panel.
- Runs = Budget ÷ Est. cost. Tokens = Runs × Total tokens — i.e. how many times you
  could repeat your configured workload, and how many tokens that adds up to, for the
  budget you enter.
- Rates for the "Long context" tier apply above a per-model input-token threshold and
  are called out with an inline "LC" badge next to the model name.
- Cache write pricing (Anthropic only) is shown in the model's hover tooltip rather
  than as its own column.

## Updating pricing data

The two fetch scripts scrape the live GitHub Copilot docs and are safe to re-run at any
time — they only touch `pricing.json` / `model_comparison.json`:

```bash
python fetch_pricing.py
python fetch_model_comparison.py
```

Then regenerate the site with `python generate_html.py --no-fetch`.
