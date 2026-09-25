#!/usr/bin/env python3
"""
generate_html.py

Generates a static index.html from pricing.json using Jinja2 templates.

Usage:
    python generate_html.py                  # fetch latest pricing + generate
    python generate_html.py --no-fetch       # use existing pricing.json + generate

Requires: Python 3.8+, jinja2
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print(
        "Error: jinja2 is required. Install it with: pip install jinja2",
        file=sys.stderr,
    )
    sys.exit(1)

# Import fetch_pricing functionality
from fetch_pricing import fetch_markdown, parse_tables

# Import fetch_model_comparison functionality
from fetch_model_comparison import fetch_markdown as fetch_markdown_comparison, parse_model_comparison

from fetch_router_pricing import build as build_router_pricing


def json_for_script(value) -> str:
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def normalize_models(
    models: list[dict], footnotes: dict[str, str] = None, comparison_summary: list[dict] = None
) -> list[dict]:
    """
    Normalize pricing.json model records for template consumption.
    - Auto-detect preview status from "(preview)" in model name
    - Strip "(preview)" suffix from display name
    - Map "Tier": None -> "Default"
    - Add missing cacheWrite as None
    - Attach footnote text from footnotes dict
    - Merge comparison data (taskArea, excelsAt, furtherReadingUrl)
    """
    if footnotes is None:
        footnotes = {}
    if comparison_summary is None:
        comparison_summary = []

    # Build a lookup map for comparison data by model name
    comparison_by_name = {}
    for entry in comparison_summary:
        model_name = entry.get("model", "")
        if model_name:
            comparison_by_name[model_name] = entry

    normalized = []
    for m in models:
        model_name = m.get("Model", "")

        # Detect preview status from name suffix
        is_preview_in_name = "(preview)" in model_name
        if is_preview_in_name:
            # Strip suffix for display
            model_name = model_name.replace(" (preview)", "").strip()

        # Determine final status
        release_status = m.get("Release status", "GA")
        if is_preview_in_name:
            status = "preview"
        elif release_status == "Public preview":
            status = "preview"
        else:
            status = "GA"

        # Map tier
        tier = m.get("Tier")
        if tier is None or tier == "None":
            tier = "Default"

        # Resolve footnotes
        footnote_text = None
        if "_footnotes" in m and m["_footnotes"]:
            # Use the first footnote reference
            fn_id = m["_footnotes"][0]
            footnote_text = footnotes.get(fn_id)

        # Merge comparison data
        comparison_data = comparison_by_name.get(model_name, {})
        task_area = comparison_data.get("taskArea", None)
        excels_at = comparison_data.get("excelsAt", None)
        further_reading_url = comparison_data.get("furtherReadingUrl", None)

        normalized.append(
            {
                "name": model_name,
                "provider": m.get("provider", "Unknown"),
                "category": m.get("Category", "Versatile"),
                "status": status,
                "tier": tier,
                "input": m.get("Input", 0.0),
                "cached": m.get("Cached input", 0.0),
                "cacheWrite": m.get("Cache write"),
                "output": m.get("Output", 0.0),
                "footnote": footnote_text,
                "taskArea": task_area,
                "excelsAt": excels_at,
                "furtherReadingUrl": further_reading_url,
            }
        )

    return normalized


def main():
    parser = argparse.ArgumentParser(
        description="Generate static index.html from pricing data."
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip fetching; use existing pricing.json and model_comparison.json on disk",
    )
    args = parser.parse_args()

    pricing_path = Path(__file__).parent / "pricing.json"
    comparison_path = Path(__file__).parent / "model_comparison.json"
    router_pricing_path = Path(__file__).parent / "router-pricing.json"

    # Fetch pricing if not --no-fetch
    if not args.no_fetch:
        print("Fetching latest pricing data...")
        try:
            markdown = fetch_markdown(
                "https://docs.github.com/api/article/body"
                "?pathname=/en/copilot/reference/copilot-billing/models-and-pricing"
            )
            models, footnotes = parse_tables(markdown)
            from datetime import date

            today = date.today().isoformat()
            output = {"fetchDate": today, "models": models}
            if footnotes:
                output["footnotes"] = footnotes
            pricing_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(f"Updated {pricing_path}")
        except Exception as e:
            print(
                f"Warning: pricing fetch failed ({e}), will try to use existing pricing.json",
                file=sys.stderr,
            )
            if not pricing_path.exists():
                print("Error: pricing.json not found and fetch failed", file=sys.stderr)
                sys.exit(1)

    # Fetch model comparison if not --no-fetch
    if not args.no_fetch:
        print("Fetching latest model comparison data...")
        try:
            markdown_comp = fetch_markdown_comparison(
                "https://docs.github.com/api/article/body"
                "?pathname=/en/copilot/reference/ai-models/model-comparison"
            )
            comp_data = parse_model_comparison(markdown_comp)
            from datetime import date

            today = date.today().isoformat()
            output_comp = {
                "fetchDate": today,
                "summary": comp_data["summary"],
                "tasks": comp_data["tasks"],
            }
            comparison_path.write_text(json.dumps(output_comp, indent=2), encoding="utf-8")
            print(f"Updated {comparison_path}")
        except Exception as e:
            print(
                f"Warning: model comparison fetch failed ({e}), will try to use existing model_comparison.json",
                file=sys.stderr,
            )
            if not comparison_path.exists():
                print("Warning: model_comparison.json not found, continuing without comparison data", file=sys.stderr)

    # Refresh router catalogs as one aggregate so each source can fall back independently.
    if not args.no_fetch:
        print("Fetching router pricing data...")
        try:
            previous = None
            if router_pricing_path.exists():
                previous = json.loads(router_pricing_path.read_text(encoding="utf-8"))
            router_output = build_router_pricing(previous)
            router_pricing_path.write_text(
                json.dumps(router_output, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Updated {router_pricing_path}")
        except Exception as e:
            print(
                f"Warning: router fetch failed ({e}), will use existing router-pricing.json",
                file=sys.stderr,
            )
            if not router_pricing_path.exists():
                print("Error: router-pricing.json not found", file=sys.stderr)
                sys.exit(1)

    # Load pricing.json
    if not pricing_path.exists():
        print(f"Error: {pricing_path} not found", file=sys.stderr)
        sys.exit(1)

    pricing_data = json.loads(pricing_path.read_text(encoding="utf-8"))
    fetch_date = pricing_data.get("fetchDate", "unknown")
    raw_models = pricing_data.get("models", [])
    footnotes = pricing_data.get("footnotes", {})

    # Load model_comparison.json if available
    comparison_summary = []
    task_guide = []
    if comparison_path.exists():
        comparison_data = json.loads(comparison_path.read_text(encoding="utf-8"))
        comparison_summary = comparison_data.get("summary", [])
        task_guide = comparison_data.get("tasks", [])

    # Normalize models with comparison data merged
    models = normalize_models(raw_models, footnotes, comparison_summary)

    # Set up Jinja2
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("page.html.j2")

    # Render
    html = template.render(
        fetchDate=fetch_date,
        models_json=json.dumps(models, indent=2),
        task_guide_json=json.dumps(task_guide, indent=2),
    )

    # Write output
    copilot_out = Path(__file__).parent / "docs" / "copilot.html"
    copilot_out.write_text(html, encoding="utf-8")
    print(f"Generated {copilot_out} ({len(models)} models)")

    # Render the landing hub to the site root.
    landing_template = env.get_template("landing.html.j2")
    landing_html = landing_template.render()
    landing_out = Path(__file__).parent / "docs" / "index.html"
    landing_out.write_text(landing_html, encoding="utf-8")
    print(f"Generated {landing_out}")

    if not router_pricing_path.exists():
        print("Error: router-pricing.json not found", file=sys.stderr)
        sys.exit(1)

    router_data = json.loads(router_pricing_path.read_text(encoding="utf-8"))
    offers = router_data.get("offers", [])
    if not offers:
        print("Error: router-pricing.json has no offers", file=sys.stderr)
        sys.exit(1)
    routers = router_data.get("routers", [])
    exchange_rate = router_data.get("exchangeRate")
    router_template = env.get_template("router-pricing.html.j2")
    router_html = router_template.render(
        generatedAt=router_data.get("generatedAt", "unknown"),
        routers=routers,
        staleRouters=[
            f"{router['name']} (fetched {router.get('fetchedAt', 'unknown')[:10]})"
            for router in routers
            if router.get("stale")
        ],
        omittedRouters=[
            omitted.get("id", "unknown")
            for omitted in router_data.get("omittedRouters", [])
        ],
        exchangeRate=exchange_rate,
        models_json=json_for_script(offers),
        routers_json=json_for_script(routers),
        exchange_rate_json=json_for_script(exchange_rate),
    )
    router_html = "\n".join(line.rstrip() for line in router_html.splitlines()) + "\n"
    router_out = Path(__file__).parent / "docs" / "router-pricing.html"
    router_out.write_text(router_html, encoding="utf-8")
    print(f"Generated {router_out} ({len(offers)} router model offers)")

    redirect_template = env.get_template("cortecs-redirect.html.j2")
    cortecs_out = Path(__file__).parent / "docs" / "cortecs.html"
    cortecs_out.write_text(redirect_template.render(), encoding="utf-8")
    print(f"Generated compatibility redirect {cortecs_out}")

    # Render the provider comparison page from cached providers.json.
    # Loaded unconditionally so --no-fetch still regenerates the page.
    providers_path = Path(__file__).parent / "providers.json"
    if providers_path.exists():
        providers_data = json.loads(providers_path.read_text(encoding="utf-8"))
        providers = providers_data.get("providers", [])
        providers_template = env.get_template("provider-compare.html.j2")
        providers_html = providers_template.render(providers=providers)
        providers_out = Path(__file__).parent / "docs" / "provider-compare.html"
        providers_out.write_text(providers_html, encoding="utf-8")
        print(f"Generated {providers_out} ({len(providers)} providers)")
    else:
        print("Warning: providers.json not found, skipping provider comparison page", file=sys.stderr)

    # Render the AI strategies page.
    strategies_template = env.get_template("strategies.html.j2")
    strategies_html = strategies_template.render()
    strategies_out = Path(__file__).parent / "docs" / "strategies.html"
    strategies_out.write_text(strategies_html, encoding="utf-8")
    print(f"Generated {strategies_out}")


if __name__ == "__main__":
    main()
