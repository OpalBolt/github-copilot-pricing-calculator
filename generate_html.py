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

# Import fetch_cortecs functionality
from fetch_cortecs import fetch_json as fetch_cortecs_json, validate as validate_cortecs, API_URL as CORTECS_URL


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
    cortecs_path = Path(__file__).parent / "cortecs.json"

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

    # Fetch Cortecs models if not --no-fetch
    if not args.no_fetch:
        print("Fetching Cortecs models data...")
        try:
            cortecs_payload = fetch_cortecs_json(CORTECS_URL)
            cortecs_models = validate_cortecs(cortecs_payload)
            from datetime import date

            cortecs_output = {
                "fetchDate": date.today().isoformat(),
                "currency": "EUR",
                "source": CORTECS_URL,
                "models": cortecs_models,
            }
            cortecs_path.write_text(json.dumps(cortecs_output, indent=2), encoding="utf-8")
            print(f"Updated {cortecs_path}")
        except Exception as e:
            print(
                f"Warning: Cortecs fetch failed ({e}), will try to use existing cortecs.json",
                file=sys.stderr,
            )
            if not cortecs_path.exists():
                print("Warning: cortecs.json not found, skipping Cortecs page", file=sys.stderr)

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
    output_path = Path(__file__).parent / "docs/index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Generated {output_path} ({len(models)} models)")

    # Render the Cortecs page from cortecs.json (if present).
    # Server-side default order: cheapest input price first; client sort lands later.
    if cortecs_path.exists():
        cortecs_data = json.loads(cortecs_path.read_text(encoding="utf-8"))
        cortecs_models = sorted(
            cortecs_data.get("models", []),
            key=lambda m: (m["pricing"]["input_token"], m["pricing"]["output_token"], m["id"]),
        )
        cortecs_template = env.get_template("cortecs.html.j2")
        cortecs_html = cortecs_template.render(
            fetchDate=cortecs_data.get("fetchDate", "unknown"),
            source=cortecs_data.get("source", CORTECS_URL),
            models=cortecs_models,
        )
        cortecs_out = Path(__file__).parent / "docs" / "cortecs.html"
        cortecs_out.write_text(cortecs_html, encoding="utf-8")
        print(f"Generated {cortecs_out} ({len(cortecs_models)} models)")


if __name__ == "__main__":
    main()
