#!/usr/bin/env python3
"""
Self-check for slices 03-05 (budget, token mix, subscription credit math, filters & sort).

The compute lives in client JS (no JS runner here), so this pins the two
things that CAN break silently and the JS depends on:

  1. The template -> JS data contract: every paygo row carries numeric
     data-input-price / data-cached-price / data-output-price, every
     subscription row carries data-mult-* plus three .sub-price cells for
     the JS to fill, and both have an .effective-tokens cell.
  2. The formulas as a Python reference: recompute blended price and
     tokens-per-budget for paygo, and credits/tokens/effective-price for
     subscription rows, against hand-derived constants; assert free models
     short-circuit to "Free" and off-peak doubles effective tokens.

Run:  python3 test_provider_compare.py
Expects docs/provider-compare.html already generated (python generate_html.py --no-fetch).
"""
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = (ROOT / "docs" / "provider-compare.html").read_text(encoding="utf-8")

# Default controls from the template: budget $10, mix 30/50/20, Lite tier, peak
BUDGET, INPUT_PCT, CACHED_PCT, OUTPUT_PCT = 10, 30, 50, 20


def extract_rows(html: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr data-provider-id=.*?</tr>", html, re.S):
        def attr(name):
            m = re.search(rf'{name}="([^"]*)"', tr)
            return m.group(1) if m else None
        rows.append({
            "pricing_type": attr("data-pricing-type"),
            "model": attr("data-model-id"),
            "tier": attr("data-tier"),
            "provider_id": attr("data-provider-id"),
            "input_price": attr("data-input-price"),
            "cached_price": attr("data-cached-price"),
            "output_price": attr("data-output-price"),
            "mult_input": attr("data-mult-input"),
            "mult_cached": attr("data-mult-cached"),
            "mult_output": attr("data-mult-output"),
            "effective": "effective-tokens" in tr,
            "sub_prices": len(re.findall(r'class="num sub-price"', tr)),
        })
    return rows


def blended(row, ip=INPUT_PCT, cp=CACHED_PCT, op=OUTPUT_PCT):
    return (ip * float(row["input_price"])
            + cp * float(row["cached_price"])
            + op * float(row["output_price"])) / 100


def main() -> int:
    rows = extract_rows(HTML)
    assert len(rows) == 25, f"expected 25 rows, got {len(rows)}"  # 16 paygo + 3 tiers × 3 models

    paygo = [r for r in rows if r["pricing_type"] == "paygo"]
    subs = [r for r in rows if r["pricing_type"] == "subscription"]
    assert len(paygo) == 16 and len(subs) == 9

    for r in paygo:
        assert r["tier"] == "", "paygo rows must carry an empty data-tier"
        assert all(r[k] is not None for k in ("input_price", "cached_price", "output_price")), r["model"]
        assert float(r["input_price"]) >= 0 and float(r["cached_price"]) >= 0 and float(r["output_price"]) >= 0
        assert r["effective"], f"{r['model']} missing .effective-tokens cell"

    for r in subs:
        assert r["tier"] != "", "subscription rows must carry a data-tier"
        assert r["provider_id"] == "zai-devpack"
        assert all(r[k] is not None for k in ("mult_input", "mult_cached", "mult_output")), r["model"]
        assert all(r[k] is None for k in ("input_price", "cached_price", "output_price")), r["model"]
        assert r["effective"]
        assert r["sub_prices"] == 3, f"{r['model']} tier {r['tier']} must have 3 .sub-price cells for the JS to fill"

    by_model = {r["model"]: r for r in rows if r["pricing_type"] == "paygo"}

    # Paygo reference: blended_price = Σ pct×price; tokens = budget × 1M / blended
    def tokens_per_budget(r):
        b = blended(r)
        assert b > 0
        return BUDGET * 1_000_000 / b

    # Hand-derived: deepseek-v4-flash @ 30/50/20 → blended 0.0994
    flash = by_model["deepseek-v4-flash"]
    assert math.isclose(blended(flash), 0.0994, rel_tol=1e-9)
    assert math.isclose(tokens_per_budget(flash), 100_603_621.7, rel_tol=1e-6)

    # glm-5.2 (expensive) @ 30/50/20 → blended 1.43
    glm52 = by_model["glm-5.2"]
    assert math.isclose(blended(glm52), 1.43, rel_tol=1e-9)
    assert math.isclose(tokens_per_budget(glm52), 6_993_006.99, rel_tol=1e-6)

    # Free model: all-zero prices must short-circuit (JS shows "Free", never divides)
    for name in ("glm-4.7-flash", "glm-4.5-flash"):
        free = by_model[name]
        assert free["input_price"] == "0.0" and free["cached_price"] == "0.0" and free["output_price"] == "0.0"
        assert blended(free) == 0.0

    # ── Subscription math reference (mirrors the JS formula) ──
    # weekly_cost = monthly/4.33; weighted_mult = Σ pct/100 × mult;
    # credits_per_1M = weighted_mult × 100; tokens/week = credits / (credits_per_1M) × 1M;
    # effective $/1M = weekly_cost / (tokens_per_week / 1M); tokens = budget / price × 1M.
    def sub_math(model, tier, budget=BUDGET, mix=(INPUT_PCT, CACHED_PCT, OUTPUT_PCT), off_peak=False):
        ip, cp, op = mix
        weekly_cost = tier["monthly_usd"] / 4.33
        weighted = ip / 100 * model["mult_input"] + cp / 100 * model["mult_cached"] + op / 100 * model["mult_output"]
        credits_per_1m = weighted * 1_000_000 / 10_000
        if off_peak:
            credits_per_1m *= 0.5
        tokens_per_week = tier["weekly_credits"] / credits_per_1m * 1_000_000
        price_per_1m = weekly_cost / (tokens_per_week / 1_000_000)
        return price_per_1m, budget / price_per_1m * 1_000_000

    # Hand-derived: Lite glm-5.2 @ 30/50/20 → 772 credits/1M, $0.32092/1M, 31.16M tokens
    lite = {"monthly_usd": 18, "weekly_credits": 10000}
    glm52_sub = {"mult_input": 6.9, "mult_cached": 1.7, "mult_output": 24.0}
    price, tokens = sub_math(glm52_sub, lite)
    assert math.isclose(price, 0.3209237875, rel_tol=1e-9), price
    assert math.isclose(tokens, 31_160_046.06, rel_tol=1e-6), tokens

    # Off-peak halves credit consumption → halves $/1M, doubles effective tokens
    price_off, tokens_off = sub_math(glm52_sub, lite, off_peak=True)
    assert math.isclose(price_off, price / 2, rel_tol=1e-9)
    assert math.isclose(tokens_off, 2 * tokens, rel_tol=1e-9)

    # Tier scaling: Max (140K credits, $168) beats Lite on tokens/$
    max_tier = {"monthly_usd": 168, "weekly_credits": 140000}
    _, tokens_max = sub_math(glm52_sub, max_tier)
    assert tokens_max > tokens

    # Free subscription model (all-zero multipliers) short-circuits before dividing
    free_sub = {"mult_input": 0.0, "mult_cached": 0.0, "mult_output": 0.0}
    assert free_sub["mult_input"] + free_sub["mult_cached"] + free_sub["mult_output"] == 0.0
    assert "Free" in HTML and "mi === 0" in HTML


    # ── Filters & sort contract (slice 05) ──
    # The behavior lives in client JS, so pin the template -> JS wiring:
    # toggle/search/chips exist, every column header is sortable, and rows
    # carry the default_visible + provider-name the filters read.
    assert 'id="show-all-models"' in HTML and 'id="show-all-label"' in HTML
    assert 'id="model-search"' in HTML
    assert 'id="provider-chips"' in HTML
    for col in ("provider", "plan", "model", "input", "cached", "output", "effective"):
        assert re.search(rf'<th class="sortable(?: num)?" data-col="{col}"', HTML), f"missing sortable column {col}"
    assert HTML.count('<span class="sort-icon">↕</span>') == 7

    prov_data = json.loads((ROOT / "providers.json").read_text(encoding="utf-8"))["providers"]
    for p in prov_data:
        assert f'data-provider="{p["id"]}"' in HTML, f"missing chip for {p['id']}"
    assert HTML.count('class="filter-chip active"') == len(prov_data)
    expected_hidden = sum(1 for p in prov_data for m in p["models"] if not m.get("default_visible", True))
    assert expected_hidden > 0, "providers.json should have hidden-by-default models for the toggle to matter"
    # row attrs (the JS selector string also contains 'data-default-visible="false"', so match the full attr pair)
    assert HTML.count('data-default-visible="false" data-provider-name="') == expected_hidden
    assert HTML.count('data-provider-name="') == len(rows)

    print(f"OK: {len(paygo)} paygo rows, {len(subs)} subscription rows, formula constants verified")
    print(f"OK: {expected_hidden} hidden-by-default models, filters/sort wiring present")

    return 0


if __name__ == "__main__":
    sys.exit(main())
