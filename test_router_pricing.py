#!/usr/bin/env python3
"""Focused checks for the aggregate router data and generated calculator."""

import json
import math
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import fetch_router_pricing
from fetch_router_pricing import (
    _cached_router,
    _openrouter_rates,
    _per_million_rates,
    _rates,
    now_utc,
)

ROOT = Path(__file__).parent
DATA = ROOT / "router-pricing.json"
HTML = ROOT / "docs" / "router-pricing.html"
REDIRECT = ROOT / "docs" / "cortecs.html"


def test_rate_helpers():
    free = _rates(0, 0, 0)
    assert free["input"] == free["cached"] == free["output"] == 0
    assert free["cachedFallback"] is False

    fallback = _rates(2, 4)
    assert fallback["cached"] == 2
    assert fallback["cachedFallback"] is True

    per_token = _per_million_rates(
        {"prompt": "0.000002", "completion": "0.000004"},
        native_currency="USD",
    )
    assert per_token["input"] == 2
    assert per_token["output"] == 4
    assert per_token["cached"] == 2


def test_openrouter_conversion():
    converted = _openrouter_rates(
        {"pricing": {"prompt": "0.000002", "completion": "0.000006"}},
        usd_per_eur=2,
    )
    assert converted["native"]["input"] == 2
    assert converted["input"] == 1
    assert converted["output"] == 3
    assert converted["cached"] == 1


def test_seven_day_router_fallback():
    fetched_at = now_utc().isoformat()
    previous = {
        "routers": [{"id": "cortecs", "fetchedAt": fetched_at}],
        "offers": [{"router": "cortecs", "key": "cortecs:x"}],
    }
    cached = _cached_router(previous, "cortecs", RuntimeError("offline"), fetched_at)
    assert cached is not None
    metadata, offers = cached
    assert metadata["stale"] is True
    assert metadata["fetchedAt"] == fetched_at
    assert offers == previous["offers"]

    previous["routers"][0]["fetchedAt"] = (
        now_utc() - timedelta(days=8)
    ).isoformat()
    assert _cached_router(previous, "cortecs", RuntimeError("offline"), fetched_at) is None


def test_stale_openrouter_keeps_its_exchange_rate():
    fetched_at = now_utc().isoformat()
    previous = {
        "exchangeRate": {"usdPerEur": 1.1, "observationDate": "2026-09-20"},
        "routers": [{"id": "openrouter", "fetchedAt": fetched_at}],
        "offers": [{"router": "openrouter", "key": "openrouter:x"}],
    }
    with (
        patch.object(
            fetch_router_pricing,
            "fetch_ecb_rate",
            return_value={"usdPerEur": 1.2, "observationDate": "2026-09-24"},
        ),
        patch.object(
            fetch_router_pricing,
            "fetch_cortecs",
            side_effect=RuntimeError("offline"),
        ),
        patch.object(
            fetch_router_pricing,
            "fetch_eurouter",
            side_effect=RuntimeError("offline"),
        ),
        patch.object(
            fetch_router_pricing,
            "fetch_openrouter",
            side_effect=RuntimeError("offline"),
        ),
    ):
        output = fetch_router_pricing.build(previous)
    assert output["exchangeRate"] == previous["exchangeRate"]
    assert output["routers"][0]["stale"] is True


def test_aggregate_contract():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    router_ids = {router["id"] for router in data["routers"]}
    assert router_ids == {"cortecs", "eurouter", "openrouter"}
    assert data["omittedRouters"] == []
    assert data["currency"] == "EUR"
    assert data["exchangeRate"]["usdPerEur"] > 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["exchangeRate"]["observationDate"])

    offers = data["offers"]
    assert offers
    assert len({offer["key"] for offer in offers}) == len(offers)
    assert {offer["router"] for offer in offers} == router_ids
    assert any(offer["eu"] is None for offer in offers)
    assert any(offer["eu"] is not None for offer in offers)

    for offer in offers:
        assert offer["key"] == f"{offer['router']}:{offer['modelId']}"
        assert offer["owner"] == offer["owner"].strip().lstrip("~").lower()
        assert set(offer["capabilities"]) == {"reasoning", "tools", "vision", "audio"}
        for mode in ("default", "eu"):
            prices = offer[mode]
            if prices is None:
                continue
            for field in ("input", "cached", "output"):
                assert isinstance(prices[field], (int, float))
                assert math.isfinite(prices[field]) and prices[field] >= 0
            if prices["cachedFallback"]:
                assert prices["cached"] == prices["input"]

    eurouter_offers = [item for item in offers if item["router"] == "eurouter"]
    assert any(offer["modelId"] == "claude-opus-4-8" for offer in eurouter_offers)
    assert {offer["default"]["nativeCurrency"] for offer in eurouter_offers} == {
        "EUR",
        "USD",
    }
    for offer in eurouter_offers:
        assert offer["eu"] == offer["default"]
        if offer["default"]["nativeCurrency"] == "USD":
            assert math.isclose(
                offer["default"]["input"],
                offer["default"]["native"]["input"] / data["exchangeRate"]["usdPerEur"],
            )

    assert {
        offer["owner"]
        for offer in offers
        if offer["owner"].replace("~", "") == "google"
    } == {"google"}

    rate = data["exchangeRate"]["usdPerEur"]
    for offer in (item for item in offers if item["router"] == "openrouter"):
        for mode in ("default", "eu"):
            prices = offer[mode]
            if prices is None:
                continue
            assert prices["nativeCurrency"] == "USD"
            assert math.isclose(prices["input"], prices["native"]["input"] / rate)


def test_generated_pages():
    html = HTML.read_text(encoding="utf-8")
    redirect = REDIRECT.read_text(encoding="utf-8")
    for marker in (
        "AI Router Price Calculator",
        'id="eu-routing-filter"',
        'id="router-filters"',
        'data-router="cortecs"',
        'data-router="eurouter"',
        'data-router="openrouter"',
        'data-filter="reasoning"',
        'data-filter="tools"',
        'data-filter="vision"',
        'data-filter="audio"',
        "Business or Enterprise",
        "Tokens per calculation",
        "Budget (€)",
        'id="creator-filter"',
        'id="creator-options"',
        'id="minimum-runs-filter"',
        'id="hide-free-filter"',
        "Model creator",
        "state.minimumRuns",
        "state.hideFree",
        "prices.input === 0 && prices.cached === 0 && prices.output === 0",
        "model.owner ||",
        "cache not published",
        "Cache rate not published",
        "This is an estimate, not a published cache price",
        "Free offer:",
        "Cache-price fallback does not change the estimate",
        'aria-label="Table legend"',
        "Cortecs EU catalog",
        "EUrouter baseline",
        "OpenRouter EU region",
        "EU Router Price",
        "EU routing meaning:",
        "Not listed for this router model offer",
        "Unavailable with EU routing",
        "Listed at the router's recorded fetch time",
        "const ALL_MODELS =",
    ):
        assert marker in html
    assert "ZDR" not in html
    assert "Input €/1M" not in html
    assert "Cached €/1M" not in html
    assert "Output €/1M" not in html
    assert 'class="capabilities-col"' in html
    assert "#router-table { table-layout: fixed; min-width: 0;" in html
    assert "@media (max-width: 1000px)" in html
    assert 'http-equiv="refresh"' in redirect
    assert 'rel="canonical" href="router-pricing.html"' in redirect
    assert "window.location.replace('router-pricing.html')" in redirect


def main():
    test_rate_helpers()
    test_openrouter_conversion()
    test_seven_day_router_fallback()
    test_stale_openrouter_keeps_its_exchange_rate()
    test_aggregate_contract()
    test_generated_pages()
    print("OK - router adapters, aggregate data, generated page, and redirect")


if __name__ == "__main__":
    main()
