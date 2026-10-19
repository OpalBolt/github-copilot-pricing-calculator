#!/usr/bin/env python3
"""Focused checks for the aggregate model-pricing data and generated page."""

import json
import math
import re
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import fetch_model_pricing
from fetch_model_pricing import _cached_seller
from sources import SOURCES
from sources.deepinfra import _deepinfra_rates, fetch_deepinfra_listings
from sources.eurouter import fetch_eurouter_listings
from sources.helpers import _rates, listing_from_offer, now_utc
from sources.opencode import fetch_opencode_listings
from sources.openrouter import fetch_openrouter_listings
from sources.deepseek_direct import fetch_deepseek_direct_listings

ROOT = Path(__file__).parent
DATA = ROOT / "model-pricing.json"
HTML = ROOT / "docs" / "model-pricing.html"
HUB = ROOT / "docs" / "index.html"

ALL_SELLERS = {
    "cortecs",
    "eurouter",
    "openrouter",
    "opencode",
    "deepinfra",
    "deepseek-direct",
    "zai-direct",
    "claude-direct",
    "openai-direct",
}
SELLER_KINDS = {
    "cortecs": "router",
    "eurouter": "router",
    "openrouter": "router",
    "opencode": "gateway",
    "deepinfra": "gateway",
    "deepseek-direct": "first-party",
    "zai-direct": "first-party",
    "claude-direct": "first-party",
    "openai-direct": "first-party",
}


def _offer(**overrides) -> dict:
    """A minimal router-shaped offer to feed through the listing helper."""
    offer = {
        "key": "test-seller:x",
        "router": "test-seller",
        "routerName": "Test Seller",
        "modelId": "x",
        "name": "X",
        "owner": "~qwen",
        "description": "d",
        "releaseDate": None,
        "contextSize": 128_000,
        "capabilities": {
            "reasoning": True,
            "tools": False,
            "vision": False,
            "audio": False,
        },
        "providers": ["Nebius"],
        "euProviders": [],
        "default": {
            "input": 1.0,
            "cached": 0.5,
            "output": 2.0,
            "cachedFallback": False,
            "nativeCurrency": "USD",
            "native": {"input": 2.0, "cached": 1.0, "output": 4.0},
        },
        "pricingTiers": [],
        "eu": {"input": 1.0, "cached": 0.5, "output": 2.0},
        "quantization": "fp4",
        "priceNote": "offer note",
    }
    offer.update(overrides)
    return offer


def test_registry_pages():
    router_pages = {sid for sid, m in SOURCES.items() if "router" in m["pages"]}
    global_pages = {sid for sid, m in SOURCES.items() if "global" in m["pages"]}
    assert router_pages == ALL_SELLERS - {"opencode", "deepinfra"}
    assert global_pages == ALL_SELLERS
    assert {m["sellerKind"] for m in SOURCES.values()} == set(SELLER_KINDS.values())
    assert {sid: m["sellerKind"] for sid, m in SOURCES.items()} == SELLER_KINDS


def test_listing_from_offer():
    listing = listing_from_offer(_offer())
    assert listing["seller"] == "test-seller"
    assert listing["sellerName"] == "Test Seller"
    assert listing["creator"] == "Alibaba"
    assert listing["rates"]["input"] == 1.0
    assert listing["rates"]["native"]["input"] == 2.0
    assert listing["capabilities"] == {
        "reasoning": True,
        "tools": False,
        "vision": False,
        "audio": False,
    }
    # EU-page fields do not leak into listings.
    for field in (
        "router",
        "routerName",
        "owner",
        "providers",
        "euProviders",
        "eu",
        "quantization",
        "direct",
    ):
        assert field not in listing
    assert listing_from_offer(_offer(), price_note="listing note")["priceNote"] == (
        "listing note"
    )
    assert listing_from_offer(_offer())["priceNote"] == "offer note"

    # EUR-native offers get their native rates filled with the EUR values.
    eur = listing_from_offer(
        _offer(
            default={**_rates(3, 6), "nativeCurrency": "EUR"},
        )
    )
    assert eur["rates"]["nativeCurrency"] == "EUR"
    assert eur["rates"]["native"] == {"input": 3, "cached": 3, "output": 6}


def test_listing_notes_name_the_sellers_own_source():
    eurouter_offers = [
        _offer(
            key="eurouter:a",
            router="eurouter",
            routerName="EUrouter",
            modelId="a",
            priceNote="EUR Router Price published by EUrouter.",
            default={
                "input": 1.0,
                "cached": 1.0,
                "output": 2.0,
                "cachedFallback": False,
                "nativeCurrency": "EUR",
            },
        ),
        _offer(
            key="eurouter:b",
            router="eurouter",
            routerName="EUrouter",
            modelId="b",
            priceNote="USD Router Price published by EUrouter and converted "
            "with the listed ECB rate.",
            default={
                "input": 1.0,
                "cached": 1.0,
                "output": 2.0,
                "cachedFallback": False,
                "nativeCurrency": "USD",
                "native": {"input": 2.0, "cached": 2.0, "output": 4.0},
            },
        ),
    ]
    with patch("sources.eurouter.fetch_eurouter", return_value=eurouter_offers):
        listings = fetch_eurouter_listings(None)
    assert listings[0]["priceNote"] == "EUR price published in EUrouter's catalog."
    assert listings[1]["priceNote"] == (
        "USD price published in EUrouter's catalog and converted with the "
        "listed ECB rate."
    )
    assert all("Router Price" not in listing["priceNote"] for listing in listings)

    with patch(
        "sources.openrouter.fetch_openrouter",
        return_value=[
            _offer(
                key="openrouter:a",
                router="openrouter",
                routerName="OpenRouter",
                modelId="a",
                priceNote="USD Router Price converted with the listed ECB rate.",
            )
        ],
    ):
        listing = fetch_openrouter_listings({"usdPerEur": 1.1})[0]
    assert "Router Price" not in listing["priceNote"]
    assert "OpenRouter" in listing["priceNote"]

    with patch(
        "sources.opencode.fetch_opencode",
        return_value=[
            _offer(
                key="opencode:a",
                router="opencode",
                routerName="OpenCode Zen",
                modelId="a",
                priceNote="USD Router Price published in OpenCode's model "
                "catalog and converted with the listed ECB rate.",
            )
        ],
    ):
        listing = fetch_opencode_listings({"usdPerEur": 1.1})[0]
    assert "models.dev" in listing["priceNote"]
    assert "Router Price" not in listing["priceNote"]

    with patch(
        "sources.deepseek_direct.fetch_deepseek_direct",
        return_value=[
            _offer(
                key="deepseek-direct:a",
                router="deepseek-direct",
                routerName="DeepSeek API",
                modelId="a",
                priceNote="Direct USD API peak price published by DeepSeek "
                "and converted with the listed ECB rate. This is not a "
                "routed offer.",
            )
        ],
    ):
        listing = fetch_deepseek_direct_listings({"usdPerEur": 1.1})[0]
    assert "DeepSeek" in listing["priceNote"]
    assert "routed offer" not in listing["priceNote"]


def test_deepinfra_adapter():
    """The committed DeepInfra catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without per-token input
    and output prices are skipped, not broken."""
    fixture = ROOT / "fixtures" / "deepinfra-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.deepinfra.fetch_json", return_value=payload):
        listings = fetch_deepinfra_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V4-Pro-0813",
        "zai-org/GLM-5.3",
        "moonshotai/Kimi-K3",
    }

    # DeepInfra's pricing page quotes these as "$ per 1M input/output
    # tokens" in dollars: the native rates pass through unmultiplied and the
    # ECB rate converts them.
    llama = by_id["meta-llama/Llama-3.3-70B-Instruct-Turbo"]
    assert llama["key"] == "deepinfra:meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert llama["seller"] == "deepinfra"
    assert llama["sellerName"] == "DeepInfra"
    assert llama["creator"] == "Meta"
    assert llama["contextSize"] == 131072
    assert llama["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": False,
        "audio": False,
    }
    assert llama["rates"]["nativeCurrency"] == "USD"
    assert llama["rates"]["native"] == {
        "input": 0.1,
        "cached": 0.1,
        "output": 0.32,
    }
    assert math.isclose(llama["rates"]["input"], 0.05)
    assert math.isclose(llama["rates"]["cached"], 0.05)
    assert math.isclose(llama["rates"]["output"], 0.16)
    assert llama["rates"]["cachedFallback"] is True

    kimi = by_id["moonshotai/Kimi-K3"]
    assert kimi["creator"] == "Moonshot AI"
    assert kimi["rates"]["native"] == {
        "input": 2.8499999999999996,
        "cached": 0.285,
        "output": 14.25,
    }
    assert math.isclose(kimi["rates"]["input"], 1.425)
    assert math.isclose(kimi["rates"]["cached"], 0.1425)
    assert kimi["rates"]["cachedFallback"] is False
    assert kimi["capabilities"] == {
        "reasoning": True,
        "tools": False,
        "vision": True,
        "audio": False,
    }

    # Canonical creator spelling from the id prefixes.
    assert by_id["deepseek-ai/DeepSeek-V4-Pro-0813"]["creator"] == "DeepSeek"
    assert by_id["zai-org/GLM-5.3"]["creator"] == "Z.ai"
    assert by_id["zai-org/GLM-5.3"]["capabilities"]["reasoning"] is True

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "DeepInfra" in listing["priceNote"]
        and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced token rows normalize to zero
    # rates, and the catalog's zero-price rows (TTS, per character) stay out
    # of the token-priced listings.
    zeros = _deepinfra_rates(
        {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0},
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    assert "XiaomiMiMo/MiMo-V2.5-tts" not in by_id


def test_seven_day_seller_fallback():
    fetched_at = now_utc().isoformat()
    previous = {
        "sellers": [{"id": "cortecs", "fetchedAt": fetched_at}],
        "listings": [{"seller": "cortecs", "key": "cortecs:x"}],
    }
    cached = _cached_seller(previous, "cortecs", RuntimeError("offline"), fetched_at)
    assert cached is not None
    metadata, listings = cached
    assert metadata["stale"] is True
    assert metadata["fetchedAt"] == fetched_at
    assert listings == previous["listings"]

    previous["sellers"][0]["fetchedAt"] = (
        now_utc() - timedelta(days=8)
    ).isoformat()
    assert _cached_seller(previous, "cortecs", RuntimeError("offline"), fetched_at) is None


@contextmanager
def _patch_adapters(**behaviors):
    """Patch the build's ECB fetch and all nine listings adapters. Values
    are return values for `ok`, exceptions for failing sources."""
    ecb = behaviors.pop("ecb", {"usdPerEur": 1.1, "observationDate": "2026-10-16"})
    patches = [
        patch.object(fetch_model_pricing, "fetch_ecb_rate", **ecb),
    ]
    for source_id, behavior in behaviors.items():
        adapter = f"fetch_{source_id.replace('-', '_')}_listings"
        if isinstance(behavior, Exception):
            patches.append(
                patch.object(fetch_model_pricing, adapter, side_effect=behavior)
            )
        else:
            patches.append(
                patch.object(fetch_model_pricing, adapter, return_value=behavior)
            )
    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        yield


def _listing(seller: str, index: int = 0) -> dict:
    return {
        "key": f"{seller}:m{index}",
        "seller": seller,
        "sellerName": f"Seller {seller}",
        "modelId": f"m{index}",
        "name": f"M{index}",
        "creator": "OpenAI",
        "capabilities": {
            "reasoning": False,
            "tools": False,
            "vision": False,
            "audio": False,
        },
        "rates": {
            "input": 1,
            "cached": 1,
            "output": 1,
            "cachedFallback": False,
            "nativeCurrency": "USD",
            "native": {"input": 1, "cached": 1, "output": 1},
        },
        "pricingTiers": [],
        "priceNote": "Test price.",
    }


def test_broken_source_fails_in_isolation():
    adapters = {
        source_id: [_listing(source_id)] for source_id in ALL_SELLERS
    }
    adapters["cortecs"] = RuntimeError("offline")
    with _patch_adapters(**adapters):
        output = fetch_model_pricing.build({})
    assert {seller["id"] for seller in output["sellers"]} == ALL_SELLERS - {"cortecs"}
    assert output["omittedSellers"] == [{"id": "cortecs", "reason": "offline"}]
    assert {listing["seller"] for listing in output["listings"]} == (
        ALL_SELLERS - {"cortecs"}
    )
    assert all(not seller["stale"] for seller in output["sellers"])


def test_build_fails_only_without_usable_data():
    adapters = {
        source_id: RuntimeError("offline") for source_id in ALL_SELLERS
    }
    with _patch_adapters(**adapters):
        try:
            fetch_model_pricing.build({})
        except RuntimeError as error:
            assert "no model pricing data is usable" in str(error)
        else:
            raise AssertionError("build should fail without usable data")


def test_stale_seller_keeps_its_exchange_rate():
    fetched_at = now_utc().isoformat()
    previous = {
        "exchangeRate": {"usdPerEur": 1.1, "observationDate": "2026-09-20"},
        "sellers": [{"id": "openrouter", "fetchedAt": fetched_at}],
        "listings": [_listing("openrouter")],
    }
    adapters = {
        source_id: RuntimeError("offline") for source_id in ALL_SELLERS
    }
    with _patch_adapters(**adapters):
        output = fetch_model_pricing.build(previous)
    assert output["exchangeRate"] == previous["exchangeRate"]
    assert [seller["id"] for seller in output["sellers"]] == ["openrouter"]
    assert output["sellers"][0]["stale"] is True
    assert [listing["seller"] for listing in output["listings"]] == ["openrouter"]


def test_ecb_failure_keeps_rate_optional_sellers():
    adapters = {
        "cortecs": [_listing("cortecs")],
        "eurouter": [_listing("eurouter")],
    }
    for source_id in ALL_SELLERS - {"cortecs", "eurouter"}:
        adapters[source_id] = RuntimeError("unused")
    with _patch_adapters(
        ecb={"side_effect": RuntimeError("ECB offline")},
        **adapters,
    ):
        output = fetch_model_pricing.build(
            {"exchangeRate": {"usdPerEur": 1.05, "observationDate": "2026-09-01"}}
        )
    assert [seller["id"] for seller in output["sellers"]] == ["cortecs", "eurouter"]
    assert output["exchangeRate"] == {
        "usdPerEur": 1.05,
        "observationDate": "2026-09-01",
    }
    assert {
        item["id"] for item in output["omittedSellers"]
    } == ALL_SELLERS - {"cortecs", "eurouter"}
    assert all("ECB" in item["reason"] for item in output["omittedSellers"])


def test_aggregate_contract():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    sellers = data["sellers"]
    seller_ids = {seller["id"] for seller in sellers}
    assert seller_ids == ALL_SELLERS
    assert data["omittedSellers"] == []
    assert data["currency"] == "EUR"
    assert data["exchangeRate"]["usdPerEur"] > 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["exchangeRate"]["observationDate"])
    assert {seller["id"]: seller["sellerKind"] for seller in sellers} == SELLER_KINDS
    # The global dataset serializes only the spec'd seller fields; the EU
    # page's baseline marker and catalog pointer stay registry-side.
    for field in ("kind", "catalogSource", "euClaim", "pages"):
        assert all(field not in seller for seller in sellers)
    assert all(seller["fetchedAt"] for seller in sellers)

    listings = data["listings"]
    assert listings
    assert len({listing["key"] for listing in listings}) == len(listings)
    assert {listing["seller"] for listing in listings} == seller_ids

    # Row-count sanity: every seller contributes listings, the big catalogs
    # are the big ones, and the counts add up to the flat table.
    counts = {seller_id: 0 for seller_id in seller_ids}
    for listing in listings:
        counts[listing["seller"]] += 1
        assert listing["key"] == f"{listing['seller']}:{listing['modelId']}"
        assert listing["creator"] == listing["creator"].strip().lstrip("~")
        assert set(listing["capabilities"]) == {"reasoning", "tools", "vision", "audio"}
        assert listing["priceNote"]
        rates = listing["rates"]
        for field in ("input", "cached", "output"):
            assert isinstance(rates[field], (int, float))
            assert math.isfinite(rates[field]) and rates[field] >= 0
            native = rates["native"]
            assert isinstance(native[field], (int, float))
            assert math.isfinite(native[field]) and native[field] >= 0
        if rates["cachedFallback"]:
            assert rates["cached"] == rates["input"]
    assert all(count > 0 for count in counts.values())
    assert counts["openrouter"] == max(counts.values())
    assert counts["openrouter"] > 100
    assert counts["cortecs"] > 50
    assert counts["eurouter"] > 50
    assert sum(counts.values()) == len(listings) >= 700

    # Rate plausibility: USD-native listings convert with the build's ECB
    # rate; EUR-native listings carry their EUR rates as the native rates.
    rate = data["exchangeRate"]["usdPerEur"]
    for listing in listings:
        rates = listing["rates"]
        if rates["nativeCurrency"] == "USD":
            assert math.isclose(rates["input"], rates["native"]["input"] / rate)
            assert math.isclose(rates["output"], rates["native"]["output"] / rate)
        else:
            assert rates["nativeCurrency"] == "EUR"
            assert rates["native"] == {
                field: rates[field] for field in ("input", "cached", "output")
            }

    native_by_seller = {
        seller["id"]: seller["nativeCurrency"] for seller in sellers
    }
    assert native_by_seller["cortecs"] == "EUR"
    assert native_by_seller["eurouter"] == "mixed"
    assert native_by_seller["openrouter"] == "USD"
    assert native_by_seller["opencode"] == "USD"
    assert native_by_seller["deepinfra"] == "USD"
    assert {
        native_by_seller[sid]
        for sid in ("deepseek-direct", "zai-direct", "claude-direct", "openai-direct")
    } == {"USD"}

    first_party = [
        listing
        for listing in listings
        if SELLER_KINDS[listing["seller"]] == "first-party"
    ]
    assert {listing["seller"] for listing in first_party} == {
        "claude-direct",
        "deepseek-direct",
        "openai-direct",
        "zai-direct",
    }
    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in first_party
    )

    eurouter = [listing for listing in listings if listing["seller"] == "eurouter"]
    assert any(listing["modelId"] == "claude-opus-4-8" for listing in eurouter)
    assert {listing["rates"]["nativeCurrency"] for listing in eurouter} == {
        "EUR",
        "USD",
    }

    # Canonical creator spelling stays single across all sellers.
    for key, label in (
        ("moonshotai", "Moonshot AI"),
        ("mistralai", "Mistral AI"),
        ("zai", "Z.ai"),
    ):
        assert {
            listing["creator"]
            for listing in listings
            if re.sub(r"[^a-z0-9]+", "", listing["creator"].lower()) == key
        } == {label}

    # Zen listings name models.dev as their price source (ADR 0003).
    zen = [listing for listing in listings if listing["seller"] == "opencode"]
    assert zen
    assert all("models.dev" in listing["priceNote"] for listing in zen)

    tiered = [listing for listing in listings if listing["pricingTiers"]]
    assert {"openai-direct:gpt-5.4", "openai-direct:gpt-5.5"} <= {
        listing["key"] for listing in tiered
    }
    for listing in tiered:
        for tier in listing["pricingTiers"]:
            assert tier["contextAbove"] > 0
            assert tier["nativeCurrency"] == "USD"
            assert math.isclose(tier["input"], tier["native"]["input"] / rate)
            if tier["cachedFallback"]:
                assert tier["cached"] == tier["input"]


def test_generated_page():
    html = HTML.read_text(encoding="utf-8")
    for marker in (
        "Model Price Calculator",
        'id="seller-filters"',
        'data-seller="cortecs"',
        'data-seller="eurouter"',
        'data-seller="openrouter"',
        'data-seller="opencode"',
        'data-seller="deepinfra"',
        'data-seller="deepseek-direct"',
        'data-seller="zai-direct"',
        'data-seller="claude-direct"',
        'data-seller="openai-direct"',
        'id="model-table"',
        'data-col="sellerName"',
        'data-col="name"',
        'data-col="creator"',
        'data-col="cost"',
        'class="capabilities-col"',
        'data-filter="reasoning"',
        'data-filter="tools"',
        'data-filter="vision"',
        'data-filter="audio"',
        "Tokens per calculation",
        "Budget (€)",
        "Model creator",
        'id="creator-filter"',
        'id="creator-options"',
        'id="minimum-runs-filter"',
        'id="hide-free-filter"',
        'id="search-input"',
        'aria-label="Table legend"',
        "state.minimumRuns",
        "state.hideFree",
        "searchTerms.every(term => haystack.includes(term))",
        "MAX_COMPARE = 5",
        'id="compare-tray"',
        "toggleCompare",
        "const ALL_MODELS =",
        "const base = model.rates",
        "contextTokens > tier.contextAbove",
        "pricingTiers.reduce",
        '€${fmt(n)}',
        "First-party",
        "Gateway",
        "cache rate not published",
        "Cache rate not published",
        "Free listing:",
        "Cache-price fallback does not change the estimate",
        "Long-context pricing:",
        "Price provenance:",
        "ECB conversion:",
        "Listed at the Seller's recorded fetch time",
        "The same model can appear as several listings",
        "never merges or groups them",
        "unrounded ECB reference rate",
        "dropped after seven days",
        "sellerOf(model)?.stale",
    ):
        assert marker in html
    # Zero grouping anywhere: no group column, no merged-model markup, and no
    # cheapest-per-model aggregate.
    assert 'data-col="group"' not in html
    assert "group-row" not in html
    assert "cheapest per model" not in html
    # EU-page-only concepts stay off the global page.
    assert "router-chip" not in html
    assert "no-eu-chip" not in html
    assert "model.eu" not in html
    assert "euClaim" not in html

    hub = HUB.read_text(encoding="utf-8")
    assert 'href="model-pricing.html"' in hub
    assert "Model Price Calculator" in hub


def main():
    test_registry_pages()
    test_listing_from_offer()
    test_listing_notes_name_the_sellers_own_source()
    test_deepinfra_adapter()
    test_seven_day_seller_fallback()
    test_broken_source_fails_in_isolation()
    test_build_fails_only_without_usable_data()
    test_stale_seller_keeps_its_exchange_rate()
    test_ecb_failure_keeps_rate_optional_sellers()
    test_aggregate_contract()
    test_generated_page()
    print("OK - listing helpers, adapters, aggregate data, and generated page")


if __name__ == "__main__":
    main()
