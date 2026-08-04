#!/usr/bin/env python3
"""
Self-check for slice 03 (budget and token mix).

The compute lives in client JS (no JS runner here), so this pins the two
things that CAN break silently and the JS depends on:

  1. The template -> JS data contract: every paygo row carries numeric
     data-input-price / data-cached-price / data-output-price, every
     subscription row carries data-mult-*, and both have an
     .effective-tokens cell.
  2. The formula itself, as a Python reference: recompute blended price and
     tokens-per-budget from the rendered row attributes with the default
     mix (30/50/20) and budget ($10), assert hand-derived constants, and
     assert free models short-circuit to "Free" while subscription rows are
     left alone (placeholder for slice 04).

Run:  python3 test_provider_compare.py
Expects docs/provider-compare.html already generated (python generate_html.py --no-fetch).
"""
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = (ROOT / "docs" / "provider-compare.html").read_text(encoding="utf-8")

# Default controls from the template: budget $10, mix 30/50/20
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
            "input_price": attr("data-input-price"),
            "cached_price": attr("data-cached-price"),
            "output_price": attr("data-output-price"),
            "mult_input": attr("data-mult-input"),
            "mult_cached": attr("data-mult-cached"),
            "mult_output": attr("data-mult-output"),
            "effective": "effective-tokens" in tr,
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
        assert all(r[k] is not None for k in ("mult_input", "mult_cached", "mult_output")), r["model"]
        assert all(r[k] is None for k in ("input_price", "cached_price", "output_price")), r["model"]
        assert r["effective"]

    by_model = {r["model"]: r for r in rows if r["pricing_type"] == "paygo"}

    # Formula reference: blended_price = Σ pct×price; tokens = budget × 1M / blended
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

    # Subscription rows must be left as placeholders: no price attrs to compute from
    assert subs and all(r["mult_input"] for r in subs)

    print(f"OK: {len(paygo)} paygo rows, {len(subs)} subscription rows, formula constants verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
