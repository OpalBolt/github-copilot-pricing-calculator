#!/usr/bin/env python3
"""
Self-check for slice 05 (filters, search, and row badges).

The interactivity is client JS (no JS runner here), so this pins the Python ->
JS data contract the badges/filters depend on, plus the controls markup:

  1. Each rendered model carries `capabilities` (reasoning/tools/vision/audio
     booleans) and `quant` (the cheapest provider's quantization), derived once
     in generate_html.py.
  2. Capability source is consistent (plan.md "Edge cases"): vision/audio from
     input_modalities, reasoning/tools from supported_features — cross-checked
     against cortecs.json.
  3. The heavy-quant rule (plan.md "Edge cases"): the row chips only fp4/int4,
     the compressions that explain a low headline price. Full-quality quants
     stay quiet; the drill-down still has every provider's quant.
  4. The filter chips, search box, column toggles, sortable headers, no-results
     fallback, and live row-count are all present in the markup.

Run:  python3 test_cortecs_filters_badges.py
Expects docs/cortecs.html already generated (python generate_html.py --no-fetch).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = ROOT / "docs" / "cortecs.html"
DATA = ROOT / "cortecs.json"

HEAVY_QUANTS = {"fp4", "int4"}
CAP_KEYS = ("reasoning", "tools", "vision", "audio")


def extract_models(html: str) -> list[dict]:
    m = re.search(r"const ALL_MODELS = (\[.*?\]);", html, re.DOTALL)
    assert m, "ALL_MODELS block not found in rendered cortecs.html"
    return json.loads(m.group(1))


def expected_caps(src: dict) -> dict:
    """Mirror of generate_html.py _capabilities: one source per capability."""
    mods = set(src.get("input_modalities", []))
    feats = set(src.get("supported_features", []))
    return {
        "vision": "image" in mods,
        "audio": "audio" in mods,
        "reasoning": "reasoning" in feats,
        "tools": "tools" in feats,
    }


def expected_quant(src: dict):
    """Mirror of generate_html.py _cheapest_quant: cheapest-tier provider's quant,
    preferring an aggressive one when several providers tie at the cheapest price."""
    top = src["pricing"]
    tier = []
    for pd in src.get("providers_details", {}).values():
        pp = pd.get("pricing", {})
        if (top.get("input_token") == pp.get("input_token")
                and top.get("output_token") == pp.get("output_token")):
            q = pd.get("quantization")
            if q:
                tier.append(q)
    heavy = sorted(q for q in tier if q in HEAVY_QUANTS)
    if heavy:
        return heavy[0]
    return sorted(tier)[0] if tier else None


def main():
    assert HTML.exists(), f"missing {HTML} — run: python generate_html.py --no-fetch"
    html = HTML.read_text(encoding="utf-8")
    models = extract_models(html)
    raw = {m["id"]: m for m in json.loads(DATA.read_text(encoding="utf-8"))["models"]}
    assert models, "no models rendered"

    # ── 1. Each model carries the badge fields ───────────────────────
    for m in models:
        assert "capabilities" in m, f"{m['id']}: missing capabilities"
        for k in CAP_KEYS:
            assert k in m["capabilities"], f"{m['id']}: capabilities missing {k}"
            assert isinstance(m["capabilities"][k], bool), f"{m['id']}: {k} not bool"
        assert "quant" in m, f"{m['id']}: missing quant"

    # ── 2 + 3. Derivation matches the source; heavy rule is honest ────
    heavy_badged = 0
    for m in models:
        src = raw[m["id"]]
        assert m["capabilities"] == expected_caps(src), \
            f"{m['id']}: capabilities {m['capabilities']} != {expected_caps(src)}"
        assert m["quant"] == expected_quant(src), \
            f"{m['id']}: quant {m['quant']!r} != {expected_quant(src)!r}"
        # Badge fires exactly for the heavy compressions; full-quality stays quiet.
        is_badged = m["quant"] in HEAVY_QUANTS
        if is_badged:
            heavy_badged += 1
        # A badged model must really have a heavy cheapest tier in the source.
        tier_quants = [
            pd.get("quantization")
            for pd in src.get("providers_details", {}).values()
            if (src["pricing"].get("input_token")
                    == pd.get("pricing", {}).get("input_token")
                and src["pricing"].get("output_token")
                    == pd.get("pricing", {}).get("output_token"))
        ]
        assert is_badged == any(q in HEAVY_QUANTS for q in tier_quants), \
            f"{m['id']}: heavy-badge rule mismatch (tier={tier_quants})"
        # And a quiet model never carries fp4/int4 on the row.
        if not is_badged:
            assert m["quant"] not in HEAVY_QUANTS

    assert heavy_badged > 0, "expected at least one fp4/int4 row badge in the dataset"

    # Spot-check a known heavy case (plan.md example: kimi-k3 cheapest tier is fp4/int4).
    kimi = next((m for m in models if m["id"] == "kimi-k3"), None)
    assert kimi and kimi["quant"] in HEAVY_QUANTS, \
        f"kimi-k3 should carry a heavy-quant badge, got {kimi['quant'] if kimi else None!r}"

    # ── 4. Controls markup the JS wires up is present ────────────────
    for needle, label in [
        ('id="filter-chips"', "filter chip bar"),
        ('data-filter="sovereign"', "Sovereign-only chip"),
        ('data-filter="zdr"', "ZDR chip"),
        ('data-filter="reasoning"', "Reasoning chip"),
        ('data-filter="tools"', "Tools chip"),
        ('data-filter="vision"', "Vision chip"),
        ('data-filter="audio"', "Audio chip"),
        ('id="search-input"', "search box"),
        ('id="toggle-input-col"', "input column toggle"),
        ('id="toggle-cached-col"', "cached column toggle"),
        ('id="toggle-output-col"', "output column toggle"),
        ('id="no-results"', "no-results fallback"),
        ('id="row-count"', "live row count"),
        ('class="sortable"', "sortable headers"),
        ('data-col="cost"', "Est. cost sort header"),
    ]:
        assert needle in html, f"missing {label}: {needle!r}"

    cap_counts = {k: sum(1 for m in models if m["capabilities"][k]) for k in CAP_KEYS}
    print(f"OK — {len(models)} models, {heavy_badged} heavy-quant badges. "
          f"Capabilities: {cap_counts}.")


if __name__ == "__main__":
    sys.exit(main())
