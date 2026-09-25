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
    _creator,
    _direct_api_offer,
    _openrouter_rates,
    _opencode_owner,
    _opencode_tiers,
    _per_million_rates,
    _provider,
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


def test_opencode_tier_conversion():
    tiers = _opencode_tiers(
        {
            "tiers": [
                {
                    "input": 4,
                    "output": 12,
                    "cache_read": 1,
                    "tier": {"type": "context", "size": 200_000},
                }
            ]
        },
        usd_per_eur=2,
    )
    assert tiers[0]["contextAbove"] == 200_000
    assert tiers[0]["input"] == 2
    assert tiers[0]["cached"] == 0.5
    assert tiers[0]["output"] == 6


def test_opencode_owner():
    assert _opencode_owner({"id": "qwen3.8-flash"}) == "Alibaba"
    assert _opencode_owner({"id": "gpt-5.4"}) == "OpenAI"
    assert _opencode_owner({"id": "space-bunny-free"}) == "OpenCode"


def test_direct_api_offer():
    offer = _direct_api_offer(
        {"id": "test-direct", "name": "Test API", "owner": "Test"},
        {"id": "test-model", "input": 2, "input_cache": 0.5, "output": 6},
        {"usdPerEur": 2},
        price_note="Direct test price.",
    )
    assert offer["direct"] is True
    assert offer["eu"] is None
    assert offer["default"]["input"] == 1
    assert offer["default"]["cached"] == 0.25
    assert offer["default"]["output"] == 3


def test_organization_name_normalization():
    assert _creator("moonshotai") == "Moonshot AI"
    assert _creator("Moonshot AI") == "Moonshot AI"
    assert _creator("mistralai") == "Mistral AI"
    assert _creator("Mistral AI") == "Mistral AI"
    assert _creator("z-ai") == "Z.ai"
    assert _creator("z.ai") == "Z.ai"
    assert _creator("~google") == "Google"
    assert _creator("openai") == "OpenAI"
    assert _creator("Nvidia") == "NVIDIA"
    assert _creator("nousresearch") == "Nous Research"
    assert _creator("MiniMax") == "MiniMax AI"
    assert _creator("minimax ai") == "MiniMax AI"
    assert _creator("MiniMax AI") == "MiniMax AI"

    assert _provider("scaleway") == "Scaleway"
    assert _provider("Scaleway") == "Scaleway"
    assert _provider("Custom Provider") == "Custom Provider"


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
    assert router_ids == {
        "cortecs",
        "deepseek-direct",
        "eurouter",
        "opencode",
        "openrouter",
        "zai-direct",
    }
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
        assert offer["owner"] == offer["owner"].strip().lstrip("~")
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
        if re.sub(r"[^a-z0-9]+", "", offer["owner"].lower()) == "moonshotai"
    } == {"Moonshot AI"}
    assert {
        offer["owner"]
        for offer in offers
        if re.sub(r"[^a-z0-9]+", "", offer["owner"].lower()) == "mistralai"
    } == {"Mistral AI"}
    assert {
        offer["owner"]
        for offer in offers
        if re.sub(r"[^a-z0-9]+", "", offer["owner"].lower()) == "zai"
    } == {"Z.ai"}
    owner_labels = {}
    provider_labels = {}
    for offer in offers:
        owner_key = re.sub(r"[^a-z0-9]+", "", offer["owner"].lower())
        owner_labels.setdefault(owner_key, set()).add(offer["owner"])
        for provider in offer["providers"] + offer["euProviders"]:
            provider_key = re.sub(r"[^a-z0-9]+", "", provider.lower())
            provider_labels.setdefault(provider_key, set()).add(provider)
    assert not {
        key: labels for key, labels in owner_labels.items() if len(labels) > 1
    }
    assert not {
        key: labels for key, labels in provider_labels.items() if len(labels) > 1
    }

    rate = data["exchangeRate"]["usdPerEur"]
    for offer in (item for item in offers if item["router"] == "openrouter"):
        for mode in ("default", "eu"):
            prices = offer[mode]
            if prices is None:
                continue
            assert prices["nativeCurrency"] == "USD"
            assert math.isclose(prices["input"], prices["native"]["input"] / rate)

    opencode_offers = [item for item in offers if item["router"] == "opencode"]
    assert opencode_offers
    assert all(offer["eu"] is None for offer in opencode_offers)
    assert any(offer["pricingTiers"] for offer in opencode_offers)
    for offer in opencode_offers:
        assert offer["default"]["nativeCurrency"] == "USD"
        assert math.isclose(
            offer["default"]["input"],
            offer["default"]["native"]["input"] / rate,
        )

    direct_offers = [item for item in offers if item.get("direct")]
    assert {offer["router"] for offer in direct_offers} == {
        "deepseek-direct",
        "zai-direct",
    }
    assert all(offer["eu"] is None for offer in direct_offers)
    assert all(
        offer["default"]["nativeCurrency"] == "USD"
        for offer in direct_offers
    )


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
        'data-router="opencode"',
        'data-router="deepseek-direct"',
        'data-router="zai-direct"',
        '.router-deepseek-direct .router-chip',
        '.router-zai-direct .router-chip',
        '.router-opencode .router-chip',
        '#router-table tr.router-deepseek-direct td:first-child',
        '#router-table tr.router-opencode td:first-child',
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
        "searchTerms.every(term => haystack.includes(term))",
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
        "Direct API",
        "provider price, not routed",
        "EU Router Price",
        "EU routing meaning:",
        "Not listed for this router model offer",
        "Unavailable with EU routing",
        "Listed at the router's recorded fetch time",
        "const ALL_MODELS =",
    ):
        assert marker in html
    assert '#router-filters [data-router="opencode"]' not in html
    assert '#router-filters [data-router="cortecs"]' not in html
    assert '#router-filters [data-router="openrouter"]' not in html
    assert "ZDR" not in html
    assert "Input €/1M" not in html
    assert "Cached €/1M" not in html
    assert "Output €/1M" not in html
    assert 'class="capabilities-col"' in html
    assert "#router-table { table-layout: fixed; min-width: 0;" in html
    assert "#router-table td.model-id {" in html
    assert "overflow-wrap: anywhere" in html
    assert "td.model-id { overflow: hidden" not in html
    assert "@media (max-width: 1000px)" in html
    assert 'http-equiv="refresh"' in redirect
    assert 'rel="canonical" href="router-pricing.html"' in redirect
    assert "window.location.replace('router-pricing.html')" in redirect


def main():
    test_rate_helpers()
    test_openrouter_conversion()
    test_opencode_tier_conversion()
    test_opencode_owner()
    test_direct_api_offer()
    test_organization_name_normalization()
    test_seven_day_router_fallback()
    test_stale_openrouter_keeps_its_exchange_rate()
    test_aggregate_contract()
    test_generated_pages()
    print("OK - router adapters, aggregate data, generated page, and redirect")


if __name__ == "__main__":
    main()
