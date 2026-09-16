#!/usr/bin/env python3
"""Self-check the generated provider comparison page and pricing contracts."""

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = (ROOT / "docs" / "provider-compare.html").read_text(encoding="utf-8")
PROVIDERS = json.loads(
    (ROOT / "providers.json").read_text(encoding="utf-8")
)["providers"]


def extract_rows(html: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr[^>]*data-provider-id=.*?</tr>", html, re.S):
        def attr(name: str):
            match = re.search(rf'{name}="([^"]*)"', tr)
            return match.group(1) if match else None

        rows.append({
            "provider": attr("data-provider-id"),
            "pricing_type": attr("data-pricing-type"),
            "model": attr("data-model-id"),
            "input": attr("data-input-price"),
            "cached": attr("data-cached-price"),
            "output": attr("data-output-price"),
            "off_input": attr("data-off-peak-input-price"),
            "off_cached": attr("data-off-peak-cached-price"),
            "off_output": attr("data-off-peak-output-price"),
            "mult_input": attr("data-mult-input"),
            "mult_cached": attr("data-mult-cached"),
            "mult_output": attr("data-mult-output"),
            "default_visible": attr("data-default-visible"),
            "compare_button": 'class="cmp-btn"' in tr,
            "monthly_cost": 'class="num monthly-cost"' in tr,
        })
    return rows


def main() -> int:
    rows = extract_rows(HTML)
    by_provider = {provider["id"]: provider for provider in PROVIDERS}
    paygo = [row for row in rows if row["pricing_type"] == "paygo"]
    subscriptions = [
        row for row in rows if row["pricing_type"] == "subscription"
    ]
    # Row counts mirror providers.json — no pinned rosters; upstream model
    # changes flow through and are noticed in fetch_providers.py, not here.
    assert rows, "no model rows rendered"
    assert len(rows) == sum(len(p["models"]) for p in PROVIDERS), \
        f"expected {sum(len(p['models']) for p in PROVIDERS)} model rows, got {len(rows)}"
    assert len(paygo) == sum(
        len(p["models"]) for p in PROVIDERS if p["pricing_type"] == "paygo"
    )
    assert len(subscriptions) == sum(
        len(p["models"]) for p in PROVIDERS if p["pricing_type"] == "subscription"
    )
    assert all(row["compare_button"] and row["monthly_cost"] for row in rows)

    for row in paygo:
        assert all(row[key] is not None for key in ("input", "cached", "output"))
        assert all(float(row[key]) >= 0 for key in ("input", "cached", "output"))
    for row in subscriptions:
        assert row["provider"] == "zai-devpack"
        assert all(
            row[key] is not None
            for key in ("mult_input", "mult_cached", "mult_output")
        )

    # DeepSeek rows mirror providers.json (ids + visibility flags), and
    # off-peak prices track the provider's off_peak_multiplier from the page.
    deepseek = [row for row in paygo if row["provider"] == "deepseek"]
    assert deepseek, "no deepseek rows rendered"
    ds = by_provider["deepseek"]
    assert {row["model"] for row in deepseek} == {m["id"] for m in ds["models"]}
    visible = {m["id"]: str(m["default_visible"]).lower() for m in ds["models"]}
    mult = ds["off_peak_multiplier"]
    for row in deepseek:
        assert all(
            row[key] is not None for key in ("off_input", "off_cached", "off_output")
        )
        assert row["default_visible"] == visible[row["model"]]
        for peak_key, off_key in (
            ("input", "off_input"),
            ("cached", "off_cached"),
            ("output", "off_output"),
        ):
            assert math.isclose(
                float(row[off_key]), float(row[peak_key]) * mult, rel_tol=1e-9
            )

    for p in PROVIDERS:  # off-peak config: sane multiplier + non-empty label
        if "off_peak_multiplier" in p:
            assert 0 < p["off_peak_multiplier"] <= 1, p
            assert p["off_peak_label"], p

    assert 'id="off-peak-toggle"' in HTML
    assert "Use off-peak rates" in HTML
    assert "provider-specific schedules" in HTML
    assert "row.dataset.offPeakInputPrice !== undefined" in HTML
    assert "useOffPeak ? row.dataset.offPeakInputPrice" in HTML
    assert "function autoOffPeak()" not in HTML

    assert 'id="show-all-models"' in HTML
    assert 'id="model-search"' in HTML
    assert 'id="provider-chips"' in HTML
    assert 'id="compare-tray"' in HTML
    assert HTML.count('class="filter-chip active"') == len(PROVIDERS)
    assert HTML.count('data-provider-name="') == len(rows)

    print(
        f"OK: {len(paygo)} paygo rows, {len(subscriptions)} subscription rows; "
        "rows mirror providers.json, off-peak ratios verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
