#!/usr/bin/env python3
"""
Self-check for the provider comparison tool (budget, token mix, subscription
credit math, filters & sort, compare tray, relative cost bars).

The compute lives in client JS (no JS runner here), so this pins the
things that CAN break silently and the JS depends on:

  1. The template -> JS data contract: every paygo row carries numeric
     data-input-price / data-cached-price / data-output-price, every
     subscription row carries data-mult-* plus three .sub-price cells for
     the JS to fill, and both have .est-cost / .runs / .tokens cells plus a
     compare button. No row carries data-tier (tier is global from radios).
  2. The formulas as a Python reference: recompute blended price and
     cost-per-run for paygo, and credits/effective-price plus the monthly-cost /
     token-cap / surplus math for subscription rows, against hand-derived
     constants; assert free models short-circuit to "Free" and off-peak halves
     effective price.

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

# Default controls from the template: budget $10, 1M tokens/run, mix 30/50/20, Lite tier, peak
BUDGET, TOKENS_PER_RUN, INPUT_PCT, CACHED_PCT, OUTPUT_PCT = 10, 1_000_000, 30, 50, 20


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
            "est_cost": 'class="num est-cost"' in tr,
            "sub_prices": len(re.findall(r'class="num sub-price"', tr)),
            "cmp_btn": 'class="cmp-btn"' in tr,
        })
    return rows


def blended(row, ip=INPUT_PCT, cp=CACHED_PCT, op=OUTPUT_PCT):
    return (ip * float(row["input_price"])
            + cp * float(row["cached_price"])
            + op * float(row["output_price"])) / 100


def main() -> int:
    rows = extract_rows(HTML)
    assert len(rows) == 19, f"expected 19 rows (16 paygo + 3 subscription), got {len(rows)}"

    paygo = [r for r in rows if r["pricing_type"] == "paygo"]
    subs = [r for r in rows if r["pricing_type"] == "subscription"]
    assert len(paygo) == 16 and len(subs) == 3

    for r in paygo:
        assert r["tier"] is None, "no row may carry data-tier (tier is global from radios)"
        assert all(r[k] is not None for k in ("input_price", "cached_price", "output_price")), r["model"]
        assert float(r["input_price"]) >= 0 and float(r["cached_price"]) >= 0 and float(r["output_price"]) >= 0
        assert r["est_cost"], f"{r['model']} missing .est-cost cell"
        assert r["cmp_btn"], f"{r['model']} missing compare button"

    for r in subs:
        assert r["tier"] is None, "subscription rows carry no data-tier"
        assert r["provider_id"] == "zai-devpack"
        assert all(r[k] is not None for k in ("mult_input", "mult_cached", "mult_output")), r["model"]
        assert all(r[k] is None for k in ("input_price", "cached_price", "output_price")), r["model"]
        assert r["est_cost"]
        assert r["sub_prices"] == 3, f"{r['model']} must have 3 .sub-price cells for the JS to fill"
        assert r["cmp_btn"]

    by_model = {r["model"]: r for r in rows if r["pricing_type"] == "paygo"}

    # Paygo reference: blended_price = Σ pct×price; cost/run = blended × tokens/1M
    def cost_per_run(r):
        b = blended(r)
        assert b > 0
        return b * TOKENS_PER_RUN / 1_000_000

    # Hand-derived: deepseek-v4-flash @ 30/50/20 → blended 0.0994 → $0.0994/run
    flash = by_model["deepseek-v4-flash"]
    assert math.isclose(blended(flash), 0.0994, rel_tol=1e-9)
    assert math.isclose(cost_per_run(flash), 0.0994, rel_tol=1e-9)

    # glm-5.2 (expensive) @ 30/50/20 → blended 1.43 → $1.43/run
    glm52 = by_model["glm-5.2"]
    assert math.isclose(blended(glm52), 1.43, rel_tol=1e-9)
    assert math.isclose(cost_per_run(glm52), 1.43, rel_tol=1e-9)

    # Free model: all-zero prices must short-circuit (JS shows "Free", never divides)
    for name in ("glm-4.7-flash", "glm-4.5-flash"):
        free = by_model[name]
        assert free["input_price"] == "0.0" and free["cached_price"] == "0.0" and free["output_price"] == "0.0"
        assert blended(free) == 0.0

    # ── Subscription math reference (mirrors the JS formula) ──
    # weekly_cost = monthly/4.33; weighted_mult = Σ pct/100 × mult;
    # credits_per_1M = weighted_mult × 100; tokens/week = credits / (credits_per_1M) × 1M;
    # effective $/1M = weekly_cost / (tokens_per_week / 1M) — unchanged, fills the price columns.
    # Est. cost = tier.monthly_usd (the plan price, not derived); runs = months the budget buys;
    # tokens = runs × monthly token cap (weekly credits × 4.33); surplus = monthly_usd when
    # budget > monthly_usd (row dims Runs/Tokens: the pool is capped per subscription period).
    def sub_math(model, tier, mix=(INPUT_PCT, CACHED_PCT, OUTPUT_PCT), off_peak=False, budget=BUDGET):
        ip, cp, op = mix
        weekly_cost = tier["monthly_usd"] / 4.33
        weighted = ip / 100 * model["mult_input"] + cp / 100 * model["mult_cached"] + op / 100 * model["mult_output"]
        credits_per_1m = weighted * 1_000_000 / 10_000
        if off_peak:
            credits_per_1m *= 0.5
        tokens_per_week = tier["weekly_credits"] / credits_per_1m * 1_000_000
        price_per_1m = weekly_cost / (tokens_per_week / 1_000_000)
        runs = budget / tier["monthly_usd"]
        tokens = runs * tokens_per_week * 4.33
        surplus = tier["monthly_usd"] if budget > tier["monthly_usd"] else None
        return price_per_1m, tier["monthly_usd"], runs, tokens, surplus

    # Hand-derived: Lite glm-5.2 @ 30/50/20 → 772 credits/1M, $0.32092/1M effective.
    # Default budget $10 < $18/mo → no surplus: Est. cost $18, runs 0.56 mo, tokens = 0.56 × monthly cap.
    lite = {"monthly_usd": 18, "weekly_credits": 10000}
    glm52_sub = {"mult_input": 6.9, "mult_cached": 1.7, "mult_output": 24.0}
    price, cost, runs, tokens, surplus = sub_math(glm52_sub, lite)
    assert math.isclose(price, 0.3209237875, rel_tol=1e-9), price
    assert math.isclose(cost, 18.0, rel_tol=1e-9), cost
    assert math.isclose(runs, BUDGET / 18, rel_tol=1e-9), runs
    assert math.isclose(tokens, runs * 10000 / 772 * 1_000_000 * 4.33, rel_tol=1e-9), tokens
    assert surplus is None

    # Surplus: budget > monthly_usd → row flags surplus = monthly_usd; tokens still scale with months
    _, cost_s, runs_s, tokens_s, surplus_s = sub_math(glm52_sub, lite, budget=100)
    assert surplus_s == 18.0
    assert math.isclose(runs_s, 100 / 18, rel_tol=1e-9)
    assert math.isclose(tokens_s, runs_s * 10000 / 772 * 1_000_000 * 4.33, rel_tol=1e-9)

    # Off-peak halves credit consumption → halves $/1M, doubles monthly token cap
    price_off, _, _, tokens_off, _ = sub_math(glm52_sub, lite, off_peak=True)
    assert math.isclose(price_off, price / 2, rel_tol=1e-9)
    assert math.isclose(tokens_off, tokens * 2, rel_tol=1e-9)

    # Tier scaling: Max (140K credits, $168) beats Lite on effective price/1M
    max_tier = {"monthly_usd": 168, "weekly_credits": 140000}
    price_max, _, _, _, _ = sub_math(glm52_sub, max_tier)
    assert price_max < price

    # Free subscription model (all-zero multipliers) short-circuits before dividing
    free_sub = {"mult_input": 0.0, "mult_cached": 0.0, "mult_output": 0.0}
    assert free_sub["mult_input"] + free_sub["mult_cached"] + free_sub["mult_output"] == 0.0
    assert "Free" in HTML and "mi === 0" in HTML
    assert "surplus" in HTML and "binding constraint" in HTML  # surplus flag + cap comment pinned

    # ── Filters & sort contract ──
    # The behavior lives in client JS, so pin the template -> JS wiring:
    # toggle/search/chips exist, every column header is sortable, and rows
    # carry the default_visible + provider-name the filters read.
    assert 'id="show-all-models"' in HTML and 'id="show-all-label"' in HTML
    assert 'id="model-search"' in HTML
    assert 'id="provider-chips"' in HTML
    for col in ("provider", "plan", "model", "input", "cached", "output", "cost", "runs", "tokens", "relative"):
        assert re.search(rf'<th class="sortable[^"]*" data-col="{col}"', HTML), f"missing sortable column {col}"
    assert HTML.count('<span class="sort-icon">↕</span>') == 10

    prov_data = json.loads((ROOT / "providers.json").read_text(encoding="utf-8"))["providers"]
    for p in prov_data:
        assert f'data-provider="{p["id"]}"' in HTML, f"missing chip for {p['id']}"
    assert HTML.count('class="filter-chip active"') == len(prov_data)
    expected_hidden = sum(1 for p in prov_data for m in p["models"] if not m.get("default_visible", True))
    assert expected_hidden > 0, "providers.json should have hidden-by-default models for the toggle to matter"
    # row attrs (the JS selector string also contains 'data-default-visible="false"', so match the full attr pair)
    assert HTML.count('data-default-visible="false" data-provider-name="') == expected_hidden
    assert HTML.count('data-provider-name="') == len(rows)

    # ── New controls (slice 08) ──
    assert 'id="tokens-per-run"' in HTML
    assert 'data-profile="superuser"' in HTML and 'data-profile="regular"' in HTML
    assert 'id="compare-tray"' in HTML and 'id="tray-cards"' in HTML and 'tray-clear' in HTML
    assert "(Mon–Fri 07:00–11:00 CET)" in HTML
    assert 'timeZone: \'Europe/Paris\'' in HTML or 'timeZone: "Europe/Paris"' in HTML
    assert 'sortCol: \'relative\'' in HTML or 'sortCol: "relative"' in HTML

    print(f"OK: {len(paygo)} paygo rows, {len(subs)} subscription rows, formula constants verified")
    print(f"OK: {expected_hidden} hidden-by-default models, filters/sort/compare wiring present")

    return 0


if __name__ == "__main__":
    sys.exit(main())
