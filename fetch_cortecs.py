#!/usr/bin/env python3
"""
fetch_cortecs.py

Calls the Cortecs models API three times — the full list, the eu_native list,
and the allow_zero_data_retention list — and writes cortecs.json. The full list
gives one row per model carrying its cheapest provider's price (the API's
top-level `pricing`) plus the per-provider detail (`providers_details`); diffing
the three provider unions derives a static provider-attribute table (EU-native /
ZDR) that later slices turn into badges and filters.

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
# Filter variants for the sovereignty/ZDR derivation (slice 04). Diffing the provider
# unions across these three responses builds the static provider-attribute table.
EU_NATIVE_URL = API_URL + "&eu_native=true"
ZDR_URL = API_URL + "&allow_zero_data_retention=true"

# No pinned provider roster: the table is derived from the live API, and new or
# removed providers must flow through without a code change. self_check below
# asserts only structural invariants and prints a diff vs the previous run.

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


def union_providers(models: list[dict]) -> set[str]:
    """Union of every model's `providers` list across a response."""
    out = set()
    for m in models:
        out.update(m.get("providers", []))
    return out


def derive_providers(
    models_full: list[dict], models_eu: list[dict], models_zdr: list[dict]
) -> dict[str, dict[str, bool]]:
    """Build the static provider-attribute table from three API responses.

    A provider is EU-native only if it appears in the `eu_native=true` response,
    and ZDR only if it appears in the `allow_zero_data_retention=true` response.
    Derived once here and baked into cortecs.json — the client never recomputes it.
    """
    all_p = union_providers(models_full)
    eu = union_providers(models_eu)
    zdr = union_providers(models_zdr)
    # A flagged provider missing from the full list means the responses disagree.
    assert eu <= all_p, f"eu_native-only providers absent from full list: {sorted(eu - all_p)}"
    assert zdr <= all_p, f"zdr-only providers absent from full list: {sorted(zdr - all_p)}"
    return {
        p: {"eu_native": p in eu, "zdr": p in zdr}
        for p in sorted(all_p)
    }


def self_check(providers: dict[str, dict[str, bool]], prev: dict | None = None) -> None:
    """Structural invariants only — the roster itself is whatever the API says.

    Roster changes vs the previous cortecs.json are printed as a notice so a
    human still sees them in CI logs, but they never fail the pipeline.
    """
    assert providers, "derived provider table is empty"
    for p, a in providers.items():
        assert set(a) == {"eu_native", "zdr"}, f"provider {p!r} flags: {sorted(a)}"
        assert all(isinstance(v, bool) for v in a.values()), f"provider {p!r} flags not bools"
    if prev is not None:
        added = set(providers) - set(prev)
        removed = set(prev) - set(providers)
        flipped = {p for p in set(providers) & set(prev)
                   if providers[p] != prev[p]}
        if added or removed or flipped:
            print(f"Note: provider table changed vs previous cortecs.json: "
                  f"+{sorted(added)} -{sorted(removed)} ~{sorted(flipped)}")


def build() -> dict:
    """Three calls + derivation + self-check -> the full cortecs.json payload.

    Shared by the standalone CLI and generate_html.py so both bake the same
    provider table. Raises on any fetch/validation mismatch (callers fall back
    to the existing cortecs.json).
    """
    models_full = validate(fetch_json(API_URL))
    models_eu = validate(fetch_json(EU_NATIVE_URL))
    models_zdr = validate(fetch_json(ZDR_URL))
    providers = derive_providers(models_full, models_eu, models_zdr)
    prev_path = Path(__file__).parent / "cortecs.json"
    prev = None
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8")).get("providers")
        except (ValueError, OSError):
            pass  # unreadable previous file -> skip the change notice
    self_check(providers, prev)
    return {
        "fetchDate": date.today().isoformat(),
        "currency": "EUR",
        "source": API_URL,
        "providers": providers,
        "models": models_full,
    }


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
    parser.parse_args()

    print("Fetching Cortecs models data (3 calls: full, eu_native, zdr)...")
    output = build()
    print_summary(output["models"])
    print(f"\nProvider table: {len(output['providers'])} providers "
          f"({sum(1 for a in output['providers'].values() if a['eu_native'])} EU-native, "
          f"{sum(1 for a in output['providers'].values() if a['zdr'])} ZDR)")

    out_path = Path(__file__).parent / "cortecs.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print("\nDone. Run generate_html.py to rebuild docs/cortecs.html.")


if __name__ == "__main__":
    # Offline self-checks of the validator and the provider derivation, then fetch + write.
    try:
        validate({})  # no 'data' key -> must raise
        raise SystemExit("self-check failed: empty payload was accepted")
    except AssertionError:
        pass
    assert validate({"data": [{"id": "x", "owned_by": "o",
            "pricing": {"input_token": 1, "output_token": 2},
            "providers_details": {}}]})
    # derive_providers: a provider is EU-native/ZDR only if it shows up in that response.
    got = derive_providers(
        [{"providers": ["aki", "azure_sc"]}],
        [{"providers": ["aki"]}],
        [{"providers": ["aki", "azure_sc"]}],
    )
    assert got == {"aki": {"eu_native": True, "zdr": True},
                   "azure_sc": {"eu_native": False, "zdr": True}}, got
    # derive_providers must reject flagged providers missing from the full list.
    try:
        derive_providers([], [{"providers": ["ghost"]}], [])
        raise SystemExit("self-check failed: ghost provider accepted")
    except AssertionError:
        pass
    # self_check: structure only; roster diff prints, never raises.
    self_check({"aki": {"eu_native": True, "zdr": False}},
               prev={"aki": {"eu_native": False, "zdr": False}})
    main()
