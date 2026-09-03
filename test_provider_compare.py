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


def blended(row: dict, prefix: str = "") -> float:
    return (
        0.3 * float(row[f"{prefix}input"])
        + 0.5 * float(row[f"{prefix}cached"])
        + 0.2 * float(row[f"{prefix}output"])
    )


def main() -> int:
    rows = extract_rows(HTML)
    paygo = [row for row in rows if row["pricing_type"] == "paygo"]
    subscriptions = [
        row for row in rows if row["pricing_type"] == "subscription"
    ]
    assert len(rows) == 17, f"expected 17 model rows, got {len(rows)}"
    assert len(paygo) == 15 and len(subscriptions) == 2
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

    deepseek = [row for row in paygo if row["provider"] == "deepseek"]
    assert [row["model"] for row in deepseek] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    ]
    assert all(
        all(row[key] is not None for key in ("off_input", "off_cached", "off_output"))
        for row in deepseek
    )
    assert deepseek[-1]["default_visible"] == "false"

    flash = deepseek[0]
    assert math.isclose(blended(flash), 0.403, rel_tol=1e-12)
    assert math.isclose(blended(flash, "off_"), 0.2015, rel_tol=1e-12)
    for peak_key, off_key in (
        ("input", "off_input"),
        ("cached", "off_cached"),
        ("output", "off_output"),
    ):
        assert math.isclose(
            float(flash[off_key]), float(flash[peak_key]) * 0.5, rel_tol=1e-12
        )

    by_provider = {provider["id"]: provider for provider in PROVIDERS}
    assert by_provider["deepseek"]["off_peak_multiplier"] == 0.5
    assert (
        by_provider["deepseek"]["off_peak_label"]
        == "Outside Mon–Fri 01:00–04:00 and 06:00–10:00 UTC"
    )
    assert by_provider["zai-devpack"]["off_peak_multiplier"] == 0.5

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
        "DeepSeek peak and off-peak rates verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
