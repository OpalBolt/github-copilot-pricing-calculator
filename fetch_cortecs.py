#!/usr/bin/env python3
"""
fetch_cortecs.py

Calls the Cortecs models API and writes cortecs.json — one row per model,
each carrying its cheapest provider's price (the API's top-level `pricing`)
plus the full per-provider detail (`providers_details`) that later slices
turn into the drill-down, badges, and filters.

Usage:
    python fetch_cortecs.py              # fetch + write cortecs.json

This module's functions are importable by generate_html.py for orchestration.

Requires: Python 3.8+ (stdlib only — urllib, json)
"""

import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

API_URL = "https://api.cortecs.ai/v1/models?extended=true&currency=EUR"

# The page and every later slice depend on these being present on each model.
REQUIRED_FIELDS = ("id", "owned_by", "pricing", "providers_details")
REQUIRED_PRICING = ("input_token", "output_token")


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-cortecs/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def validate(payload: dict) -> list[dict]:
    """Return the model list, asserting it has the shape the page depends on."""
    assert isinstance(payload, dict), "response is not a JSON object"
    models = payload.get("data")
    assert isinstance(models, list) and models, "response has no models list"
    for m in models:
        for f in REQUIRED_FIELDS:
            assert f in m, f"model {m.get('id')!r} missing {f!r}"
        for p in REQUIRED_PRICING:
            assert p in m["pricing"], f"model {m['id']!r} pricing missing {p!r}"
    return models


def print_summary(models: list[dict]) -> None:
    print("\n── Cortecs models ──────────────────────────────────────────")
    for m in models[:8]:
        pr = m["pricing"]
        print(f"  {m['id']:<28} {m['owned_by']:<16} "
              f"in €{pr['input_token']:<7} out €{pr['output_token']}")
    if len(models) > 8:
        print(f"  … and {len(models) - 8} more")
    print(f"\nTotal: {len(models)} models")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Cortecs models data.")
    args = parser.parse_args()

    print("Fetching Cortecs models data...")
    payload = fetch_json(API_URL)
    models = validate(payload)
    print_summary(models)

    output = {
        "fetchDate": date.today().isoformat(),
        "currency": "EUR",
        "source": API_URL,
        "models": models,
    }

    out_path = Path(__file__).parent / "cortecs.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print("\nDone. Run generate_html.py to rebuild docs/cortecs.html.")


if __name__ == "__main__":
    # Assert-based self-check of the validator (offline), then fetch + write.
    try:
        validate({})  # no 'data' key -> must raise
        raise SystemExit("self-check failed: empty payload was accepted")
    except AssertionError:
        pass
    assert validate({"data": [{"id": "x", "owned_by": "o",
            "pricing": {"input_token": 1, "output_token": 2},
            "providers_details": {}}]})
    main()
