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
from sources.aiand import _aiand_rates, fetch_aiand_listings
from sources.aimlapi import _aimlapi_rates, fetch_aimlapi_listings
from sources.ambient import _ambient_rates, fetch_ambient_listings
from sources.chutes import _chutes_rates, fetch_chutes_listings
from sources.crossmodel import _crossmodel_rates, fetch_crossmodel_listings
from sources.deepinfra import _deepinfra_rates, fetch_deepinfra_listings
from sources.edenai import _edenai_rates, fetch_edenai_listings
from sources.empiriolabs import (
    _empiriolabs_rates,
    fetch_empiriolabs_listings,
)
from sources.engy import _engy_rates, fetch_engy_listings
from sources.eurouter import fetch_eurouter_listings
from sources.helpers import _rates, listing_from_offer, now_utc
from sources.kilo import _kilo_rates, fetch_kilo_listings
from sources.llm_gateway import _llm_gateway_rates, fetch_llmgateway_listings
from sources.novita import _novita_rates, fetch_novita_listings
from sources.nano_gpt import _nano_gpt_rates, fetch_nano_gpt_listings
from sources.opencode import fetch_opencode_listings
from sources.requesty import _requesty_rates, fetch_requesty_listings
from sources.vercel_gateway import (
    _vercel_gateway_rates,
    fetch_vercel_gateway_listings,
)
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
    "novita",
    "requesty",
    "nano-gpt",
    "vercel-gateway",
    "kilo",
    "chutes",
    "llmgateway",
    "aiand",
    "aimlapi",
    "ambient",
    "crossmodel",
    "edenai",
    "empiriolabs",
    "engy",
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
    "novita": "gateway",
    "requesty": "gateway",
    "nano-gpt": "gateway",
    "vercel-gateway": "gateway",
    "kilo": "gateway",
    "chutes": "gateway",
    "llmgateway": "gateway",
    "aiand": "gateway",
    "aimlapi": "gateway",
    "ambient": "gateway",
    "crossmodel": "gateway",
    "edenai": "gateway",
    "empiriolabs": "gateway",
    "engy": "gateway",
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
    assert router_pages == ALL_SELLERS - {
        "opencode",
        "deepinfra",
        "novita",
        "requesty",
        "nano-gpt",
        "vercel-gateway",
        "kilo",
        "chutes",
        "llmgateway",
        "aiand",
        "aimlapi",
        "ambient",
        "crossmodel",
        "edenai",
        "empiriolabs",
        "engy",
    }
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


def test_novita_adapter():
    """The committed Novita catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without prompt and
    completion prices are skipped, not broken."""
    fixture = ROOT / "fixtures" / "novita-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.novita.fetch_json", return_value=payload):
        listings = fetch_novita_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "deepseek/deepseek-v4.1-flash-1017",
        "minimax/minimax-m3",
        "meta-llama/llama-3.3-70b-instruct",
        "qwen/qwen3-omni-30b-a3b-thinking",
    }

    # Novita's pricing page quotes these same catalog rows as "$ per Mt":
    # the price_per_m_decimal values pass through unmultiplied in dollars
    # and the ECB rate converts them.
    deepseek = by_id["deepseek/deepseek-v4.1-flash-1017"]
    assert deepseek["key"] == "novita:deepseek/deepseek-v4.1-flash-1017"
    assert deepseek["seller"] == "novita"
    assert deepseek["sellerName"] == "Novita"
    assert deepseek["name"] == "DeepSeek V4.1 Flash 1017"
    assert deepseek["creator"] == "DeepSeek"
    assert deepseek["contextSize"] == 1048576
    assert deepseek["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert deepseek["rates"]["nativeCurrency"] == "USD"
    assert deepseek["rates"]["native"] == {
        "input": 0.3,
        "cached": 0.006,
        "output": 1.2,
    }
    assert math.isclose(deepseek["rates"]["input"], 0.15)
    assert math.isclose(deepseek["rates"]["cached"], 0.003)
    assert math.isclose(deepseek["rates"]["output"], 0.6)
    assert deepseek["rates"]["cachedFallback"] is False

    # Tiered-billing rows keep the base (first-tier) rates the catalog's
    # top-level pricing publishes; rows without an input_cache_read
    # component fall back to the input rate.
    minimax = by_id["minimax/minimax-m3"]
    assert minimax["creator"] == "MiniMax AI"
    assert minimax["rates"]["native"] == {
        "input": 0.3,
        "cached": 0.06,
        "output": 1.2,
    }
    assert minimax["rates"]["cachedFallback"] is False
    omni = by_id["qwen/qwen3-omni-30b-a3b-thinking"]
    assert omni["creator"] == "Alibaba"
    assert omni["rates"]["native"] == {
        "input": 0.25,
        "cached": 0.25,
        "output": 0.97,
    }
    assert omni["rates"]["cachedFallback"] is True
    assert omni["capabilities"]["audio"] is True
    assert by_id["meta-llama/llama-3.3-70b-instruct"]["creator"] == "Meta"

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Novita" in listing["priceNote"]
        and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced components normalize to zero
    # rates, and rows without prompt and completion prices stay out of the
    # token-priced listings.
    zeros = _novita_rates(
        {
            "prompt": {"price_per_m_decimal": "0"},
            "completion": {"price_per_m_decimal": "0"},
            "input_cache_read": {"price_per_m_decimal": "0"},
        },
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    assert "bunny" not in by_id
    # The integer price_per_m is the decimal quote in 1/10000 units; with
    # no input_cache_read component the cached rate falls back to input.
    integers = _novita_rates(
        {"prompt": {"price_per_m": 3000}, "completion": {"price_per_m": 12000}},
        2.0,
    )
    assert math.isclose(integers["native"]["input"], 0.3)
    assert math.isclose(integers["native"]["output"], 1.2)
    assert integers["cachedFallback"] is True


def test_requesty_adapter():
    """The committed Requesty catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without per-token input
    and output prices are skipped, not broken."""
    fixture = ROOT / "fixtures" / "requesty-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.requesty.fetch_json", return_value=payload):
        listings = fetch_requesty_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "anthropic/claude-sonnet-4-5",
        "deepinfra/deepseek-v4.1-flash-1017",
        "anthropic/claude-haiku-5-5",
        "nebius/kimi-k3",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    }

    # Requesty's API reference documents the catalog's price fields as
    # per-token USD prices ("Price per input token in USD"), so the rates
    # scale by 1,000,000 in dollars and the ECB rate converts them.
    sonnet = by_id["anthropic/claude-sonnet-4-5"]
    assert sonnet["key"] == "requesty:anthropic/claude-sonnet-4-5"
    assert sonnet["seller"] == "requesty"
    assert sonnet["sellerName"] == "Requesty"
    assert sonnet["name"] == "claude-sonnet-4-5"
    assert sonnet["creator"] == "Anthropic"
    assert sonnet["contextSize"] == 1000000
    assert sonnet["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert sonnet["rates"]["nativeCurrency"] == "USD"
    assert sonnet["rates"]["native"] == {
        "input": 3.0,
        "cached": 0.3,
        "output": 15.0,
    }
    assert math.isclose(sonnet["rates"]["input"], 1.5)
    assert math.isclose(sonnet["rates"]["cached"], 0.15)
    assert math.isclose(sonnet["rates"]["output"], 7.5)
    assert sonnet["rates"]["cachedFallback"] is False

    # Tiered rows keep the base (threshold-0) tier the top-level prices
    # publish: the catalog's 200k-prompt tier does not move the rate.
    haiku = by_id["anthropic/claude-haiku-5-5"]
    assert haiku["rates"]["native"] == {
        "input": 0.1,
        "cached": 0.01,
        "output": 0.5,
    }

    # Discount rows already publish the discounted price: the catalog's
    # discount_percentage is baked into these values, not applied by us.
    deepseek = by_id["deepinfra/deepseek-v4.1-flash-1017"]
    assert deepseek["creator"] == "DeepSeek"
    assert deepseek["rates"]["native"] == {
        "input": 0.098,
        "cached": 0.00294,
        "output": 0.294,
    }

    # Rows without a cached_price fall back to the input rate, and the
    # canonical `model_lab` spellings map to the table's creator names.
    kimi = by_id["nebius/kimi-k3"]
    assert kimi["creator"] == "Moonshot AI"
    assert kimi["rates"]["cachedFallback"] is True
    assert kimi["rates"]["cached"] == kimi["rates"]["input"]
    assert math.isclose(kimi["rates"]["input"], 1.5)

    nemotron = by_id["nvidia/nemotron-3.5-lightning-30b-a3b"]
    assert nemotron["creator"] == "NVIDIA"

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Requesty" in listing["priceNote"]
        and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: the zero-priced row normalizes to zero rates
    # with its published cached_price, so no fallback applies.
    assert nemotron["rates"]["native"] == {
        "input": 0,
        "cached": 0,
        "output": 0,
    }
    assert nemotron["rates"]["cachedFallback"] is False
    zeros = _requesty_rates(
        {"input_price": 0, "cached_price": 0, "output_price": 0}, 2.0
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without per-token input and output prices are not token-priced
    # and stay out of the listings.
    try:
        _requesty_rates({}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")


def test_nano_gpt_adapter():
    """The committed nano-gpt catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; the catalog's note-only
    varies_by_modality rows are skipped, not broken."""
    # nano-gpt's own pricing page bills text API usage "at the model's list
    # price" in USD, and the catalog rows price currency USD; the registry
    # records that verified native currency.
    assert SOURCES["nano-gpt"]["nativeCurrency"] == "USD"
    assert SOURCES["nano-gpt"]["pages"] == ("global",)

    fixture = ROOT / "fixtures" / "nano-gpt-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.nano_gpt.fetch_json", return_value=payload):
        listings = fetch_nano_gpt_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "openai/gpt-5.2",
        "moonshotai/kimi-k2-thinking",
        "openai/gpt-oss-20b",
        "bytedance/doubao-seed-character",
        "nano-gpt-help",
    }

    # The catalog prices every row `per_million_tokens` USD, so prompt and
    # completion rates pass through unmultiplied in dollars and the ECB
    # rate converts them; the cache-read field is per 1,000 tokens and
    # scales by 1,000.
    gpt = by_id["openai/gpt-5.2"]
    assert gpt["key"] == "nano-gpt:openai/gpt-5.2"
    assert gpt["seller"] == "nano-gpt"
    assert gpt["sellerName"] == "nano-gpt"
    assert gpt["name"] == "GPT 5.2"
    assert gpt["creator"] == "OpenAI"
    assert gpt["contextSize"] == 400000
    assert gpt["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert gpt["rates"]["nativeCurrency"] == "USD"
    assert gpt["rates"]["native"]["input"] == 1.75
    assert math.isclose(gpt["rates"]["native"]["cached"], 0.175)
    assert gpt["rates"]["native"]["output"] == 14.0
    assert math.isclose(gpt["rates"]["input"], 0.875)
    assert math.isclose(gpt["rates"]["cached"], 0.0875)
    assert math.isclose(gpt["rates"]["output"], 7.0)
    assert gpt["rates"]["cachedFallback"] is False

    kimi = by_id["moonshotai/kimi-k2-thinking"]
    assert kimi["creator"] == "Moonshot AI"
    assert kimi["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": False,
        "audio": False,
    }
    assert kimi["rates"]["native"]["input"] == 0.6
    assert math.isclose(kimi["rates"]["native"]["cached"], 0.15)
    assert kimi["rates"]["native"]["output"] == 2.5

    # Rows without a cache-read price fall back to the input rate, and the
    # cache-write field never stands in for the cached-input read.
    oss = by_id["openai/gpt-oss-20b"]
    assert oss["rates"]["cachedFallback"] is True
    assert oss["rates"]["cached"] == oss["rates"]["input"]
    doubao = by_id["bytedance/doubao-seed-character"]
    assert math.isclose(doubao["rates"]["native"]["cached"], 0.03)
    assert not math.isclose(doubao["rates"]["native"]["cached"], 0.003)

    # A zero price is a price: the zero-priced row normalizes to zero
    # rates instead of dropping out.
    assert by_id["nano-gpt-help"]["rates"]["native"] == {
        "input": 0,
        "cached": 0,
        "output": 0,
    }
    zeros = _nano_gpt_rates(
        {"pricing": {"prompt": 0, "completion": 0}}, 2.0
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "nano-gpt" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # Rows without prompt and completion prices (the catalog's
    # varies_by_modality note rows) are not per-million-token priced and
    # stay out of the listings.
    try:
        _nano_gpt_rates(
            {"pricing": {"currency": "USD", "note": "varies_by_modality"}}, 2.0
        )
    except ValueError:
        pass
    else:
        raise AssertionError("note-only pricing should skip the row")


def test_vercel_gateway_adapter():
    """The committed Vercel AI Gateway catalog sample normalizes to
    per-million-token USD listings converted with the ECB rate; non-text
    output rows and rows without per-token input and output prices are
    skipped, not broken."""
    # Vercel AI Gateway charges the provider's list price with zero markup
    # and bills it in US dollars (vercel.com/docs/ai-gateway/pricing); the
    # registry records that verified native currency, and the catalog feeds
    # the global page only.
    assert SOURCES["vercel-gateway"]["nativeCurrency"] == "USD"
    assert SOURCES["vercel-gateway"]["pages"] == ("global",)
    assert SOURCES["vercel-gateway"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "vercel-gateway-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.vercel_gateway.fetch_json", return_value=payload):
        listings = fetch_vercel_gateway_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "alibaba/qwen-3-14b",
        "alibaba/qwen3-coder",
        "nvidia/nemotron-3.5-lightning-free",
        "alibaba/qwen3-vl-instruct",
    }

    # Vercel's AI Gateway Model List renders the catalog's price fields as
    # dollars per 1M tokens (inputCost 0.12 for the catalog's
    # "0.00000012"), so the per-token prices scale by 1,000,000 in dollars
    # and the ECB rate converts them.
    qwen = by_id["alibaba/qwen-3-14b"]
    assert qwen["key"] == "vercel-gateway:alibaba/qwen-3-14b"
    assert qwen["seller"] == "vercel-gateway"
    assert qwen["sellerName"] == "Vercel AI Gateway"
    assert qwen["name"] == "Qwen3-14B"
    assert qwen["creator"] == "Alibaba"
    assert qwen["contextSize"] == 40960
    assert qwen["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": False,
        "audio": False,
    }
    assert qwen["rates"]["nativeCurrency"] == "USD"
    assert qwen["rates"]["native"] == {
        "input": 0.12,
        "cached": 0.12,
        "output": 0.24,
    }
    assert math.isclose(qwen["rates"]["input"], 0.06)
    assert math.isclose(qwen["rates"]["cached"], 0.06)
    assert math.isclose(qwen["rates"]["output"], 0.12)
    assert qwen["rates"]["cachedFallback"] is True

    # The catalog's input_cache_read field prices cached input per token;
    # rows publishing it use it instead of the input-rate fallback.
    coder = by_id["alibaba/qwen3-coder"]
    assert coder["rates"]["native"] == {
        "input": 0.22,
        "cached": 0.022,
        "output": 1.8,
    }
    assert coder["rates"]["cachedFallback"] is False

    # Image inputs map to the vision capability through the shared
    # capability helper.
    vl = by_id["alibaba/qwen3-vl-instruct"]
    assert vl["creator"] == "Alibaba"
    assert vl["capabilities"] == {
        "reasoning": False,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert vl["rates"]["native"] == {
        "input": 0.2,
        "cached": 0.11,
        "output": 0.88,
    }

    # A zero price is a price: the free row normalizes to zero rates
    # instead of dropping out.
    free = by_id["nvidia/nemotron-3.5-lightning-free"]
    assert free["creator"] == "NVIDIA"
    assert free["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert free["rates"]["cachedFallback"] is True

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Vercel AI Gateway" in listing["priceNote"]
        and "ECB" in listing["priceNote"]
        for listing in listings
    )
    zeros = _vercel_gateway_rates(
        {"pricing": {"input": "0", "output": "0", "input_cache_read": "0"}},
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without per-token input and output prices (the fixture's
    # embedding row, whose pricing publishes input only) are not
    # per-million-token priced and stay out of the listings.
    try:
        _vercel_gateway_rates({"pricing": {"input": "0.00000001"}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")
    # The fixture's TTS and image rows publish prices but no text output
    # modality; like the routers' build, only text-output rows list.
    assert "google/gemini-3.8-flash-tts" not in by_id
    assert "microsoft/mai-image-2.6" not in by_id


def test_kilo_adapter():
    """The committed Kilo catalog sample normalizes to per-million-token USD
    listings converted with the ECB rate; the auto-routing rows' -1 sentinel
    prices skip the row, not break the build."""
    # Kilo bills its gateway per token in US dollars with "microdollar
    # precision (1 USD = 1,000,000 microdollars)" (kilo.ai/docs/gateway/
    # usage-and-billing); the registry records that verified native
    # currency, and the catalog feeds the global page only.
    assert SOURCES["kilo"]["nativeCurrency"] == "USD"
    assert SOURCES["kilo"]["pages"] == ("global",)
    assert SOURCES["kilo"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "kilo-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.kilo.fetch_json", return_value=payload):
        listings = fetch_kilo_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "anthropic/claude-sonnet-4.5",
        "deepseek/deepseek-v3.2-exp",
        "google/gemini-3-pro-image",
        "kilo-auto/free",
        "minimax/minimax-m3.1-flash:free",
    }

    # Kilo's Usage & Billing doc derives costs from "the upstream
    # provider's pricing based on token usage", so the catalog's per-token
    # decimals scale by 1,000,000 in dollars and the ECB rate converts
    # them.
    sonnet = by_id["anthropic/claude-sonnet-4.5"]
    assert sonnet["key"] == "kilo:anthropic/claude-sonnet-4.5"
    assert sonnet["seller"] == "kilo"
    assert sonnet["sellerName"] == "Kilo"
    assert sonnet["name"] == "Anthropic: Claude Sonnet 4.5"
    assert sonnet["creator"] == "Anthropic"
    assert sonnet["contextSize"] == 1000000
    assert sonnet["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert sonnet["rates"]["nativeCurrency"] == "USD"
    assert sonnet["rates"]["native"] == {
        "input": 3.0,
        "cached": 0.3,
        "output": 15.0,
    }
    assert math.isclose(sonnet["rates"]["input"], 1.5)
    assert math.isclose(sonnet["rates"]["cached"], 0.15)
    assert math.isclose(sonnet["rates"]["output"], 7.5)
    assert sonnet["rates"]["cachedFallback"] is False

    # Rows without an input_cache_read component fall back to the input
    # rate, and the creator spelling comes from the id's vendor prefix.
    deepseek = by_id["deepseek/deepseek-v3.2-exp"]
    assert deepseek["creator"] == "DeepSeek"
    assert deepseek["rates"]["cachedFallback"] is True
    assert deepseek["rates"]["cached"] == deepseek["rates"]["input"]
    assert math.isclose(deepseek["rates"]["native"]["input"], 0.27)
    assert math.isclose(deepseek["rates"]["native"]["output"], 0.41)

    # Image inputs map to the vision capability through the shared
    # capability helper.
    image = by_id["google/gemini-3-pro-image"]
    assert image["creator"] == "Google"
    assert image["capabilities"]["vision"] is True
    assert image["rates"]["native"] == {
        "input": 2.0,
        "cached": 0.2,
        "output": 12.0,
    }

    # A zero price is a price: the free rows normalize to zero rates
    # instead of dropping out.
    free = by_id["kilo-auto/free"]
    assert free["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    # The free row's published zero cache-read price is a price, not a
    # fallback; the :free row without a cache component falls back.
    assert free["rates"]["cachedFallback"] is False
    minimax_free = by_id["minimax/minimax-m3.1-flash:free"]
    assert minimax_free["creator"] == "MiniMax AI"
    assert minimax_free["rates"]["cachedFallback"] is True

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Kilo" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    zeros = _kilo_rates(
        {"pricing": {"prompt": "0", "completion": "0", "input_cache_read": "0"}},
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # The auto-routing rows publish a -1 sentinel instead of token prices;
    # negative and missing prices are not token-priced and skip the row.
    try:
        _kilo_rates({"pricing": {"prompt": "-1", "completion": "-1"}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("negative sentinel prices should skip the row")
    try:
        _kilo_rates({"pricing": {}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")
    assert "kilo-auto/efficient" not in by_id


def test_chutes_adapter():
    """The committed Chutes catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without prompt and
    completion prices are skipped, not broken."""
    # Chutes's pricing page charges "per million tokens, separately for
    # input and output" and quotes the catalog rows as dollars per 1M
    # tokens ($0.12 per 1M tokens for pricing.prompt 0.12), with TAO only
    # an alternative payment method; the registry records that verified
    # native currency, and the catalog feeds the global page only.
    assert SOURCES["chutes"]["nativeCurrency"] == "USD"
    assert SOURCES["chutes"]["pages"] == ("global",)
    assert SOURCES["chutes"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "chutes-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.chutes.fetch_json", return_value=payload):
        listings = fetch_chutes_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "google/gemma-4-31B-turbo-TEE",
        "deepseek-ai/DeepSeek-V3.2-TEE",
        "unsloth/Mistral-Nemo-Instruct-2407-TEE",
        "Nemotron-3-Nano-Omni-30B-TEE",
    }

    # The catalog's pricing fields are already dollars per 1M tokens (the
    # pricing page quotes pricing.prompt 0.12 as "$0.12 per 1M tokens"), so
    # they pass through unmultiplied and the ECB rate converts them.
    gemma = by_id["google/gemma-4-31B-turbo-TEE"]
    assert gemma["key"] == "chutes:google/gemma-4-31B-turbo-TEE"
    assert gemma["seller"] == "chutes"
    assert gemma["sellerName"] == "Chutes"
    assert gemma["name"] == "google/gemma-4-31B-turbo-TEE"
    assert gemma["creator"] == "Google"
    assert gemma["contextSize"] == 131072
    assert gemma["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert gemma["rates"]["nativeCurrency"] == "USD"
    assert gemma["rates"]["native"] == {
        "input": 0.12,
        "cached": 0.011999999999999997,
        "output": 0.37,
    }
    assert math.isclose(gemma["rates"]["input"], 0.06)
    assert math.isclose(gemma["rates"]["cached"], 0.006)
    assert math.isclose(gemma["rates"]["output"], 0.185)
    assert gemma["rates"]["cachedFallback"] is False

    # The canonical creator spelling comes from the id's vendor prefix; the
    # catalog's owned_by field names the serving engine, not the creator.
    assert by_id["deepseek-ai/DeepSeek-V3.2-TEE"]["creator"] == "DeepSeek"
    assert by_id["unsloth/Mistral-Nemo-Instruct-2407-TEE"]["creator"] == "unsloth"
    # A slash-less id has no vendor prefix and no creator.
    assert by_id["Nemotron-3-Nano-Omni-30B-TEE"]["creator"] == ""

    # The pricing page's Context column reads context_length and falls back
    # to max_model_len when the catalog leaves it null; rows without
    # modalities and supported_features derive no capabilities.
    nemo = by_id["unsloth/Mistral-Nemo-Instruct-2407-TEE"]
    assert nemo["contextSize"] == 131072
    assert nemo["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": False,
        "audio": False,
    }

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Chutes" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced token rows normalize to zero
    # rates instead of dropping out.
    zeros = _chutes_rates(
        {"pricing": {"prompt": 0, "completion": 0, "input_cache_read": 0}},
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without an input_cache_read component fall back to the input
    # rate.
    fallback = _chutes_rates(
        {"pricing": {"prompt": "0.2", "completion": "1"}}, 2.0
    )
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # Rows without prompt and completion prices are not token-priced and
    # stay out of the listings.
    try:
        _chutes_rates({"pricing": {}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")


def test_llm_gateway_adapter():
    """The committed LLM Gateway catalog sample normalizes to
    per-million-token USD listings converted with the ECB rate; non-text
    output rows (video, embedding) are skipped, not broken."""
    # LLM Gateway's model directory renders the catalog's per-token price
    # fields as dollars per 1M tokens ("Input $0.15 /M tokens Cache Read
    # $0.075 /M tokens Output $0.6 /M tokens" for gpt-4o-mini), and the
    # pricing page bills add-ons like data retention at $0.01 per 1M
    # tokens; the registry records that verified native currency, and the
    # catalog feeds the global page only.
    assert SOURCES["llmgateway"]["nativeCurrency"] == "USD"
    assert SOURCES["llmgateway"]["pages"] == ("global",)
    assert SOURCES["llmgateway"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "llmgateway-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.llm_gateway.fetch_json", return_value=payload):
        listings = fetch_llmgateway_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "gpt-4o-mini",
        "kimi-k2-thinking",
        "deepseek-v3.2",
        "ling-3.1-flash",
        "custom",
    }

    # The catalog prices prompt, completion, and input_cache_read per token
    # in USD (gpt-4o-mini's row prices prompt "0.15e-6" where the model
    # directory quotes "$0.15 /M tokens"), so the per-token decimals scale
    # by 1,000,000 in dollars and the ECB rate converts them.
    gpt = by_id["gpt-4o-mini"]
    assert gpt["key"] == "llmgateway:gpt-4o-mini"
    assert gpt["seller"] == "llmgateway"
    assert gpt["sellerName"] == "LLM Gateway"
    assert gpt["name"] == "GPT-4o Mini"
    assert gpt["creator"] == "OpenAI"
    assert gpt["contextSize"] == 128000
    assert gpt["capabilities"] == {
        "reasoning": False,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert gpt["rates"]["nativeCurrency"] == "USD"
    assert gpt["rates"]["native"] == {
        "input": 0.15,
        "cached": 0.075,
        "output": 0.6,
    }
    assert math.isclose(gpt["rates"]["input"], 0.075)
    assert math.isclose(gpt["rates"]["cached"], 0.0375)
    assert math.isclose(gpt["rates"]["output"], 0.3)
    assert gpt["rates"]["cachedFallback"] is False

    # The canonical creator spelling comes from the catalog's family field.
    kimi = by_id["kimi-k2-thinking"]
    assert kimi["creator"] == "Moonshot AI"
    assert kimi["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": False,
        "audio": False,
    }
    assert kimi["rates"]["native"] == {
        "input": 0.6,
        "cached": 0.06,
        "output": 2.5,
    }
    deepseek = by_id["deepseek-v3.2"]
    assert deepseek["creator"] == "DeepSeek"
    assert deepseek["rates"]["native"] == {
        "input": 0.26,
        "cached": 0.13,
        "output": 0.38,
    }

    # A zero price is a price: the zero-priced rows normalize to zero rates
    # with their published zero cache-read price, so no fallback applies.
    ling = by_id["ling-3.1-flash"]
    assert ling["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert ling["rates"]["cachedFallback"] is False
    routing = by_id["custom"]
    assert routing["creator"] == "llmgateway"
    assert routing["contextSize"] == 0
    assert routing["capabilities"]["vision"] is True
    assert routing["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "LLM Gateway" in listing["priceNote"]
        and "ECB" in listing["priceNote"]
        for listing in listings
    )
    zeros = _llm_gateway_rates(
        {"pricing": {"prompt": "0", "completion": "0", "input_cache_read": "0"}},
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without a published cache-read price fall back to the input rate.
    fallback = _llm_gateway_rates(
        {"pricing": {"prompt": "0.0000002", "completion": "0.000001"}}, 2.0
    )
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # Rows without prompt and completion prices are not token-priced and
    # stay out of the listings.
    try:
        _llm_gateway_rates({"pricing": {}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")
    # The fixture's video and embedding rows publish no text output
    # modality; like the other gateway adapters, only text-output rows list.
    assert "veo-3.1-generate-preview" not in by_id
    assert "text-embedding-3-small" not in by_id


def test_aiand_adapter():
    """The committed aiand catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without per-million
    input and output prices are skipped, not broken."""
    # ai&'s pricing doc: the catalog's *_per_1m fields are "prices per 1
    # million tokens" and "Called without an API key, the endpoint returns
    # USD prices"; the registry records that verified native currency, and
    # the catalog feeds the global page only.
    assert SOURCES["aiand"]["nativeCurrency"] == "USD"
    assert SOURCES["aiand"]["pages"] == ("global",)
    assert SOURCES["aiand"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "aiand-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.aiand.fetch_json", return_value=payload):
        listings = fetch_aiand_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "deepseek-ai/deepseek-v4.1-flash",
        "zai-org/glm-5.3",
        "moonshotai/kimi-k3",
        "qwen/qwen3.8-27b",
        "motif-technologies/motif-3",
        "openai/gpt-oss-120b",
    }

    # ai&'s pricing formula bills "(input_tokens / 1_000_000) ×
    # input_per_1m", so the catalog's input_per_1m, output_per_1m, and
    # cached_input_per_1m fields pass through unmultiplied in dollars and
    # the ECB rate converts them.
    deepseek = by_id["deepseek-ai/deepseek-v4.1-flash"]
    assert deepseek["key"] == "aiand:deepseek-ai/deepseek-v4.1-flash"
    assert deepseek["seller"] == "aiand"
    assert deepseek["sellerName"] == "aiand"
    assert deepseek["name"] == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert deepseek["creator"] == "DeepSeek"
    assert deepseek["contextSize"] == 1048576
    assert deepseek["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert deepseek["rates"]["nativeCurrency"] == "USD"
    assert deepseek["rates"]["native"] == {
        "input": 0.3,
        "cached": 0.02,
        "output": 0.6,
    }
    assert math.isclose(deepseek["rates"]["input"], 0.15)
    assert math.isclose(deepseek["rates"]["cached"], 0.01)
    assert math.isclose(deepseek["rates"]["output"], 0.3)
    assert deepseek["rates"]["cachedFallback"] is False

    # The canonical creator spelling comes from the catalog's provider
    # field, "the lab that released the open weights"; the documented
    # vision, video, and document input capabilities map to vision.
    glm = by_id["zai-org/glm-5.3"]
    assert glm["creator"] == "Z.ai"
    assert glm["rates"]["native"] == {
        "input": 1.0,
        "cached": 0.3,
        "output": 4.0,
    }
    assert glm["capabilities"]["vision"] is False
    kimi = by_id["moonshotai/kimi-k3"]
    assert kimi["creator"] == "Moonshot AI"
    assert kimi["rates"]["native"] == {
        "input": 3.0,
        "cached": 0.5,
        "output": 12.5,
    }
    assert kimi["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }
    assert by_id["qwen/qwen3.8-27b"]["creator"] == "Alibaba"
    # A provider outside the alias table passes through unaliased.
    assert by_id["motif-technologies/motif-3"]["creator"] == (
        "Motif-Technologies"
    )
    assert by_id["openai/gpt-oss-120b"]["creator"] == "OpenAI"

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "aiand" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced rows normalize to zero rates
    # instead of dropping out.
    zeros = _aiand_rates(
        {
            "input_per_1m": "0",
            "output_per_1m": "0",
            "cached_input_per_1m": "0",
        },
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without a cached_input_per_1m fall back to the input rate.
    fallback = _aiand_rates({"input_per_1m": "0.2", "output_per_1m": "1"}, 2.0)
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # Rows without per-million input and output prices are not
    # per-million-token priced and stay out of the listings.
    try:
        _aiand_rates({}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-million prices should skip the row")


def test_aimlapi_adapter():
    """The committed AI/ML API catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; the same model's other-endpoint
    rows and rows without text-token input and output prices are skipped, not
    broken."""
    # AI/ML API's Complete Model List doc ends the price walkthrough with
    # "Prices are in USD and are what you are charged"; the registry
    # records that verified native currency, and the catalog feeds the
    # global page only.
    assert SOURCES["aimlapi"]["nativeCurrency"] == "USD"
    assert SOURCES["aimlapi"]["pages"] == ("global",)
    assert SOURCES["aimlapi"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "aimlapi-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.aimlapi.fetch_json", return_value=payload):
        listings = fetch_aimlapi_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "minimax/minimax-m3.1-flash",
        "google/gemini-3.8-flash",
        "reflection/beam-1.0-501b-a23b",
        "inclusionai/ling-3.1-flash",
        "openai/gpt-6-luna",
    }

    # The catalog prices text tokens by `per` basis (1000000 for these
    # rows), so the provided/cached/generated charges pass through
    # unmultiplied in dollars and the ECB rate converts them; the generated
    # reasoning phase repeats the output charge and never moves the rate.
    minimax = by_id["minimax/minimax-m3.1-flash"]
    assert minimax["key"] == "aimlapi:minimax/minimax-m3.1-flash"
    assert minimax["seller"] == "aimlapi"
    assert minimax["sellerName"] == "AI/ML API"
    assert minimax["name"] == "MiniMax M3.1 Flash"
    assert minimax["creator"] == "MiniMax AI"
    assert minimax["contextSize"] == 1000000
    assert minimax["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": True,
        "audio": False,
    }
    assert minimax["rates"]["nativeCurrency"] == "USD"
    assert minimax["rates"]["native"] == {
        "input": 0.195,
        "cached": 0.0195,
        "output": 0.78,
    }
    assert math.isclose(minimax["rates"]["input"], 0.0975)
    assert math.isclose(minimax["rates"]["cached"], 0.00975)
    assert math.isclose(minimax["rates"]["output"], 0.39)
    assert minimax["rates"]["cachedFallback"] is False

    # Per-call charges and image/video/audio token streams never stand in
    # for the text token rates.
    gemini = by_id["google/gemini-3.8-flash"]
    assert gemini["creator"] == "Google"
    assert gemini["rates"]["native"] == {
        "input": 0.975,
        "cached": 0.0975,
        "output": 4.875,
    }
    assert gemini["capabilities"]["vision"] is True
    assert gemini["capabilities"]["audio"] is False

    # Rows without a cached unit fall back to the input rate, and a
    # developer outside the alias table passes through unaliased.
    beam = by_id["reflection/beam-1.0-501b-a23b"]
    assert beam["creator"] == "Reflection"
    assert beam["rates"]["cachedFallback"] is True
    assert beam["rates"]["cached"] == beam["rates"]["input"]
    assert math.isclose(beam["rates"]["native"]["input"], 0.34385)

    # A zero price is a price: the free row's published zero cached price
    # is a price, not a fallback.
    ling = by_id["inclusionai/ling-3.1-flash"]
    assert ling["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert ling["rates"]["cachedFallback"] is False

    # The catalog lists one row per model per endpoint: the gpt-6-luna
    # fixture carries decisions, chat-completions, and responses rows, and
    # only the chat-completions row's complete prices list.
    luna = by_id["openai/gpt-6-luna"]
    assert luna["creator"] == "OpenAI"
    assert luna["rates"]["native"] == {
        "input": 0.13,
        "cached": 0.013,
        "output": 0.65,
    }
    assert luna["rates"]["cachedFallback"] is False

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "AI/ML API" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced token units normalize to zero
    # rates instead of dropping out.
    zeros = _aimlapi_rates(
        {
            "pricing": {
                "units": [
                    {"name": "token", "content": "text", "origin": "provided", "phase": "inference", "price": 0, "per": 1000000},
                    {"name": "token", "content": "text", "origin": "cached", "phase": "inference", "price": 0, "per": 1000000},
                    {"name": "token", "content": "text", "origin": "generated", "phase": "inference", "price": 0, "per": 1000000},
                ]
            }
        },
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without a cached unit fall back to the input rate.
    fallback = _aimlapi_rates(
        {
            "pricing": {
                "units": [
                    {"name": "token", "content": "text", "origin": "provided", "phase": "inference", "price": "0.2", "per": 1000000},
                    {"name": "token", "content": "text", "origin": "generated", "phase": "inference", "price": "1", "per": 1000000},
                ]
            }
        },
        2.0,
    )
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # The doc's per warning: "`1000000` for most token rates, `1000` for
    # some" — per-1000 rows scale by 1,000, not 1,000,000.
    thousands = _aimlapi_rates(
        {
            "pricing": {
                "units": [
                    {"name": "token", "content": "text", "origin": "provided", "phase": "inference", "price": 0.0195, "per": 1000},
                    {"name": "token", "content": "text", "origin": "generated", "phase": "inference", "price": 0.078, "per": 1000},
                ]
            }
        },
        2.0,
    )
    assert math.isclose(thousands["native"]["input"], 19.5)
    assert math.isclose(thousands["native"]["output"], 78)
    # Rows without text-token input and output prices (the dynamic
    # router's empty units) are not per-million-token priced and stay out
    # of the listings.
    try:
        _aimlapi_rates({"pricing": {"units": []}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")
    # The fixture's non-chat endpoint rows (the image-generations and
    # text-to-speech endpoints) stay out of the listings.
    assert "x-ai/grok-imagine-image-2.0" not in by_id
    assert "openai/tts-1" not in by_id
    assert "aimlapi/dynamic-router" not in by_id


def test_ambient_adapter():
    """The committed Ambient catalog sample normalizes to per-million-token
    USD listings converted with the ECB rate; rows without per-million input
    and output prices are skipped, not broken."""
    # Ambient's docs publish the catalog's per-model prices "as USD per
    # million tokens (pricing.input and pricing.output)" (ambient.xyz/docs/
    # build/models); the registry records that verified native currency,
    # and the catalog feeds the global page only.
    assert SOURCES["ambient"]["nativeCurrency"] == "USD"
    assert SOURCES["ambient"]["pages"] == ("global",)
    assert SOURCES["ambient"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "ambient-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.ambient.fetch_json", return_value=payload):
        listings = fetch_ambient_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "z-ai/glm-5.2",
        "qwen/qwen3.8-27b",
        "minimax/minimax-m3",
        "unsloth/qwen3.8-27b-gguf",
        "ambient/large",
    }

    # The catalog's pricing.input and pricing.output fields are already
    # dollars per 1M tokens (the docs' catalog table quotes GLM 5.2 at
    # "$0.60 / M" and "$2.00 / M" for input 0.6 and output 2.0), so they
    # pass through unmultiplied and the ECB rate converts them; the
    # input_cache_read decimal is the per-token sibling of the row's prompt
    # and completion decimals and scales by 1,000,000.
    glm = by_id["z-ai/glm-5.2"]
    assert glm["key"] == "ambient:z-ai/glm-5.2"
    assert glm["seller"] == "ambient"
    assert glm["sellerName"] == "Ambient"
    assert glm["name"] == "GLM 5.2"
    assert glm["creator"] == "Z.ai"
    assert glm["contextSize"] == 202752
    assert glm["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": False,
        "audio": False,
    }
    assert glm["rates"]["nativeCurrency"] == "USD"
    assert glm["rates"]["native"] == {
        "input": 0.6,
        "cached": 0.15,
        "output": 2.0,
    }
    assert math.isclose(glm["rates"]["input"], 0.3)
    assert math.isclose(glm["rates"]["cached"], 0.075)
    assert math.isclose(glm["rates"]["output"], 1.0)
    assert glm["rates"]["cachedFallback"] is False

    # Image inputs map to the vision capability through the shared
    # capability helper, and the id's qwen prefix maps to Alibaba.
    qwen = by_id["qwen/qwen3.8-27b"]
    assert qwen["creator"] == "Alibaba"
    assert qwen["capabilities"]["vision"] is True
    assert qwen["rates"]["native"] == {
        "input": 0.32,
        "cached": 0.16,
        "output": 3.2,
    }

    # The is_ready flag is a routing flag consumed by OpenRouter, "not a
    # served/not-served signal", so the is_ready-false row lists like the
    # rest of the catalog.
    minimax = by_id["minimax/minimax-m3"]
    assert minimax["creator"] == "MiniMax AI"
    assert minimax["rates"]["native"] == {
        "input": 0.23,
        "cached": 0.05,
        "output": 0.96,
    }

    # A zero price is a price: the GGUF row's published zero cache-read
    # price stays a zero rate instead of falling back to the input rate.
    gguf = by_id["unsloth/qwen3.8-27b-gguf"]
    assert gguf["name"] == "qwen3.8-27b-4q"
    assert gguf["creator"] == "unsloth"
    assert gguf["rates"]["native"] == {
        "input": 0.001,
        "cached": 0,
        "output": 0.001,
    }
    assert gguf["rates"]["cachedFallback"] is False
    assert gguf["capabilities"] == {
        "reasoning": False,
        "tools": True,
        "vision": False,
        "audio": False,
    }

    # The ambient/large alias lists under its own id from its own live
    # catalog entry, and a vendor prefix outside the alias table passes
    # through unaliased.
    alias = by_id["ambient/large"]
    assert alias["key"] == "ambient:ambient/large"
    assert alias["creator"] == "ambient"
    assert alias["rates"]["native"] == glm["rates"]["native"]

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Ambient" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced rows normalize to zero rates
    # instead of dropping out.
    zeros = _ambient_rates(
        {"pricing": {"input": 0, "output": 0, "input_cache_read": "0"}}, 2.0
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without an input_cache_read field fall back to the input rate.
    fallback = _ambient_rates({"pricing": {"input": "0.2", "output": 1}}, 2.0)
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # Rows without per-million input and output prices are not
    # per-million-token priced and stay out of the listings.
    try:
        _ambient_rates({"pricing": {"input": 0.2}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-million prices should skip the row")
    try:
        _ambient_rates({}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing pricing should skip the row")


def test_crossmodel_adapter():
    """The committed Crossmodel catalog sample normalizes its micro-dollar
    per-1M prices into USD listings converted with the ECB rate; the
    threshold tiers become pricingTiers and the decision rows keep their
    published zero prices."""
    # CrossModel bills a US-dollar wallet in "micro units of currency
    # (1 USD = 1,000,000 micro)" (crossmodel.ai/docs/api-reference/
    # credits); the registry records that verified native currency, and
    # the catalog feeds the global page only.
    assert SOURCES["crossmodel"]["nativeCurrency"] == "USD"
    assert SOURCES["crossmodel"]["pages"] == ("global",)
    assert SOURCES["crossmodel"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "crossmodel-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.crossmodel.fetch_json", return_value=payload):
        listings = fetch_crossmodel_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "anthropic/claude-opus-5",
        "openai/gpt-5.6-sol",
        "qwen/qwen3.7-flash",
        "gemini/gemini-3.8-flash",
        "z-ai/glm-5",
        "deepseek/deepseek-v4.1-flash",
        "cloudflare/clef",
    }

    # The catalog's input_micro_per_1m fields are micro-dollars per 1M
    # tokens (the usage API bills cost_micro "in micro units of currency
    # (1 USD = 1,000,000 micro); divide by 1,000,000"), so claude-opus-5's
    # 5,000,000 input micro and 25,000,000 output micro are the $5.00 /
    # $25.00 per 1M the site itself quotes and divide by 1,000,000 before
    # the ECB rate converts them.
    opus = by_id["anthropic/claude-opus-5"]
    assert opus["key"] == "crossmodel:anthropic/claude-opus-5"
    assert opus["seller"] == "crossmodel"
    assert opus["sellerName"] == "Crossmodel"
    assert opus["name"] == "Claude Opus 5"
    assert opus["creator"] == "Anthropic"
    assert opus["contextSize"] == 1_000_000
    assert opus["pricingTiers"] == []
    assert opus["rates"]["nativeCurrency"] == "USD"
    assert opus["rates"]["native"] == {"input": 5.0, "cached": 0.5, "output": 25.0}
    assert math.isclose(opus["rates"]["input"], 2.5)
    assert math.isclose(opus["rates"]["cached"], 0.25)
    assert math.isclose(opus["rates"]["output"], 12.5)
    assert opus["rates"]["cachedFallback"] is False
    assert opus["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }

    # The threshold tiers after the base row are long-context tiers with
    # their own rates, listed at their contextAbove like the other
    # sellers' pricingTiers.
    sol = by_id["openai/gpt-5.6-sol"]
    assert [tier["contextAbove"] for tier in sol["pricingTiers"]] == [272000]
    tier = sol["pricingTiers"][0]
    assert tier["native"] == {"input": 8.0, "cached": 0.8, "output": 30.0}
    assert math.isclose(tier["input"], 4.0)
    assert math.isclose(tier["cached"], 0.4)
    assert math.isclose(tier["output"], 15.0)
    qwen = by_id["qwen/qwen3.7-flash"]
    assert [t["contextAbove"] for t in qwen["pricingTiers"]] == [32000, 256000]
    assert qwen["creator"] == "Alibaba"
    assert qwen["rates"]["native"] == {"input": 0.04, "cached": 0.01, "output": 0.13}

    # The gemini vendor prefix maps to Google, and audio input maps to the
    # audio capability through the catalog's modalities.
    gemini = by_id["gemini/gemini-3.8-flash"]
    assert gemini["creator"] == "Google"
    assert gemini["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": True,
    }
    assert gemini["rates"]["native"] == {"input": 0.75, "cached": 0.075, "output": 3.75}

    # Decision models are "billed on input tokens only" (crossmodel.ai/
    # docs/billing), so their published zero output and cache prices stay
    # zero rates instead of falling back to the input rate, and a vendor
    # prefix outside the alias table passes through unaliased.
    clef = by_id["cloudflare/clef"]
    assert clef["name"] == "Clef"
    assert clef["creator"] == "cloudflare"
    assert clef["rates"]["native"] == {"input": 0.24, "cached": 0, "output": 0}
    assert clef["rates"]["cachedFallback"] is False
    assert clef["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": True,
        "audio": False,
    }

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Crossmodel" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero-priced rows normalize to zero rates
    # instead of dropping out.
    zeros = _crossmodel_rates(
        {
            "pricing": {
                "tiers": [
                    {
                        "threshold": 0,
                        "input_micro_per_1m": 0,
                        "output_micro_per_1m": 0,
                        "cache_read_micro_per_1m": 0,
                    }
                ]
            }
        },
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Tiers without a cache_read_micro_per_1m field fall back to the input
    # rate.
    fallback = _crossmodel_rates(
        {
            "pricing": {
                "tiers": [
                    {
                        "threshold": 0,
                        "input_micro_per_1m": 200000,
                        "output_micro_per_1m": 1000000,
                    }
                ]
            }
        },
        2.0,
    )
    assert fallback["cachedFallback"] is True
    assert fallback["cached"] == fallback["input"] == 0.1
    # Rows without input and output prices in their base tier are not
    # token-priced and stay out of the listings.
    try:
        _crossmodel_rates(
            {"pricing": {"tiers": [{"threshold": 0, "input_micro_per_1m": 200000}]}},
            2.0,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("missing output price should skip the row")
    try:
        _crossmodel_rates({}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing pricing should skip the row")


def test_edenai_adapter():
    """The committed Eden AI catalog sample normalizes its per-token USD
    prices into per-million listings converted with the ECB rate; the
    billed discounted prices win over list_pricing and zero prices are
    kept."""
    # Eden AI bills a prepaid credit balance in US dollars ("Every API
    # response includes a cost field showing the charge in USD for that
    # request", edenai.co/docs/v3/general/buying-credits); the registry
    # records that verified native currency, and the catalog feeds the
    # global page only.
    assert SOURCES["edenai"]["nativeCurrency"] == "USD"
    assert SOURCES["edenai"]["pages"] == ("global",)
    assert SOURCES["edenai"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "edenai-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.edenai.fetch_json", return_value=payload):
        listings = fetch_edenai_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "minimax/MiniMax-M3.1-Flash",
        "cohere/c4ai-aya-expanse-32b",
        "qwen/deepseek-v4.1-flash-1017",
        "google/gemini-4-argon",
        "together_ai/together/Tev1-4B-experimental",
        "google/gemma-4-31b-it",
        "google/gemini-pro-latest",
        "google/gemini-3.1-flash-lite-image",
    }

    # The catalog's *_cost_per_token fields are per-token amounts (the
    # model-listing doc's "input_cost_per_token": 1.5e-06 sample), so the
    # rates scale by 1,000,000 in dollars and the ECB rate converts them.
    minimax = by_id["minimax/MiniMax-M3.1-Flash"]
    assert minimax["key"] == "edenai:minimax/MiniMax-M3.1-Flash"
    assert minimax["seller"] == "edenai"
    assert minimax["sellerName"] == "Eden AI"
    assert minimax["name"] == "MiniMax-M3.1-Flash"
    assert minimax["creator"] == "MiniMax AI"
    assert minimax["contextSize"] is None
    assert minimax["pricingTiers"] == []
    assert minimax["rates"]["nativeCurrency"] == "USD"
    assert minimax["rates"]["native"] == {
        "input": 0.15,
        "cached": 0.015,
        "output": 0.6,
    }
    assert math.isclose(minimax["rates"]["input"], 0.075)
    assert math.isclose(minimax["rates"]["cached"], 0.0075)
    assert math.isclose(minimax["rates"]["output"], 0.3)
    assert minimax["rates"]["cachedFallback"] is False
    assert minimax["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": False,
        "audio": False,
    }

    # Rows without cache_read_input_token_cost fall back to the input
    # rate, and an owned_by outside the alias table passes through
    # unaliased.
    aya = by_id["cohere/c4ai-aya-expanse-32b"]
    assert aya["creator"] == "cohere"
    assert aya["rates"]["native"] == {"input": 0.5, "cached": 0.5, "output": 1.5}
    assert aya["rates"]["cachedFallback"] is True

    # Discounted rows bill `pricing` — `discount` is the fraction off
    # `list_pricing` — so the billed 65% rates convert, not the list
    # rates, and the catalog's audio, image, reasoning, and grounding
    # price fields stay out of the text-token rates.
    flash = by_id["qwen/deepseek-v4.1-flash-1017"]
    assert flash["creator"] == "Alibaba"
    assert math.isclose(flash["rates"]["native"]["input"], 0.0975)
    assert math.isclose(flash["rates"]["native"]["output"], 0.39)
    assert math.isclose(flash["rates"]["native"]["cached"], 0.00975)
    argon = by_id["google/gemini-4-argon"]
    assert argon["rates"]["native"] == {
        "input": 2.0,
        "cached": 0.1,
        "output": 10.0,
    }
    assert argon["contextSize"] == 1_048_576
    assert argon["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": True,
    }

    # A zero price is a price: the free rows normalize to zero rates
    # instead of dropping out.
    tev1 = by_id["together_ai/together/Tev1-4B-experimental"]
    assert tev1["rates"]["native"] == {
        "input": 0.042,
        "cached": 0.042,
        "output": 0,
    }
    assert tev1["rates"]["cachedFallback"] is True
    free = by_id["google/gemma-4-31b-it"]
    assert free["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert free["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": True,
        "audio": False,
    }

    # Alias rows (alias_of set) list like any other endpoint.
    alias = by_id["google/gemini-pro-latest"]
    assert alias["rates"]["native"] == {
        "input": 2.0,
        "cached": 0.1,
        "output": 10.0,
    }

    # Image-and-text output rows still list: the published
    # output_cost_per_token prices their text tokens.
    image = by_id["google/gemini-3.1-flash-lite-image"]
    assert image["rates"]["native"] == {
        "input": 0.25,
        "cached": 0.25,
        "output": 1.5,
    }
    assert image["capabilities"] == {
        "reasoning": True,
        "tools": False,
        "vision": True,
        "audio": False,
    }

    # Image-only rows stay out even with per-token prices published: no
    # "text" in output_modalities means no token-priced listing.
    assert "black-forest-labs/flux-2-pro" not in by_id

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Eden AI" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    zeros = _edenai_rates(
        {
            "pricing": {
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
                "cache_read_input_token_cost": 0,
            }
        },
        2.0,
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without per-token input and output prices are not
    # per-million-token priced and stay out of the listings.
    try:
        _edenai_rates({"pricing": {"input_cost_per_token": 1e-06}}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")
    # The live catalog repeats a few ids with differing rows; the listing
    # key is the id, so only the first repeat survives the dedup.
    repeated = {"object": "list", "data": [payload["data"][0], payload["data"][0]]}
    with patch("sources.edenai.fetch_json", return_value=repeated):
        assert len(fetch_edenai_listings({"usdPerEur": 2.0})) == 1
    # Differing repeats are first-wins: the re-priced duplicate never
    # overwrites the first row's rates.
    first = payload["data"][0]
    repriced = {
        **first,
        "pricing": {
            **first["pricing"],
            "input_cost_per_token": first["pricing"]["input_cost_per_token"]
            * 10,
        },
    }
    conflicting = {"object": "list", "data": [first, repriced]}
    with patch("sources.edenai.fetch_json", return_value=conflicting):
        kept = fetch_edenai_listings({"usdPerEur": 2.0})
    assert len(kept) == 1
    assert kept[0]["modelId"] == first["id"]
    assert kept[0]["rates"]["native"]["input"] == 0.15


def test_empiriolabs_adapter():
    """The committed Empirio Labs catalog sample normalizes its per-token
    USD decimal strings into per-million listings converted with the ECB
    rate; tiered rows publish pricingTiers and zero prices are kept."""
    # Empirio Labs's own pricing page states "Prices are listed and billed
    # in USD" (empiriolabs.ai/pricing); the registry records that verified
    # native currency, and the catalog feeds the global page only.
    assert SOURCES["empiriolabs"]["nativeCurrency"] == "USD"
    assert SOURCES["empiriolabs"]["pages"] == ("global",)
    assert SOURCES["empiriolabs"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "empiriolabs-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.empiriolabs.fetch_json", return_value=payload):
        listings = fetch_empiriolabs_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "glm-5-3",
        "qwen3-7-flash",
        "qwen3-7-plus:variant1",
        "qwen3-5-omni-flash",
        "glm-4-5-flash",
        "exa-search",
        "janus-pro-deepseek",
        "perplexity-sonar",
    }

    # The catalog's prompt, completion, and input_cache_read fields are
    # per-token decimals (pricing_rows renders "0.0000014" as "$1.40 per
    # 1M prompt tokens"), so the rates scale by 1,000,000 in dollars and
    # the ECB rate converts them.
    glm = by_id["glm-5-3"]
    assert glm["key"] == "empiriolabs:glm-5-3"
    assert glm["seller"] == "empiriolabs"
    assert glm["sellerName"] == "Empirio Labs"
    assert glm["name"] == "GLM 5.3"
    assert glm["creator"] == "Z.ai"
    assert glm["contextSize"] == 1_000_000
    assert glm["pricingTiers"] == []
    assert glm["rates"]["nativeCurrency"] == "USD"
    assert glm["rates"]["native"] == {
        "input": 1.4,
        "cached": 1.4,
        "output": 4.4,
    }
    assert math.isclose(glm["rates"]["input"], 0.7)
    assert math.isclose(glm["rates"]["cached"], 0.7)
    assert math.isclose(glm["rates"]["output"], 2.2)
    assert glm["rates"]["cachedFallback"] is False
    assert glm["capabilities"] == {
        "reasoning": True,
        "tools": True,
        "vision": False,
        "audio": False,
    }

    # Tiered rows publish a pricing list: the threshold-free first dict is
    # the listing's base rate, and the min_context dicts become pricingTiers
    # with per-million native and converted rates.
    flash = by_id["qwen3-7-flash"]
    assert flash["creator"] == "Alibaba"
    assert flash["rates"]["native"] == {
        "input": 0.03,
        "cached": 0.006,
        "output": 0.13,
    }
    tiers = flash["pricingTiers"]
    assert [tier["contextAbove"] for tier in tiers] == [32_000, 256_000]
    assert tiers[0]["native"] == {
        "input": 0.1,
        "cached": 0.02,
        "output": 0.4,
    }
    assert tiers[0]["nativeCurrency"] == "USD"
    assert math.isclose(tiers[0]["input"], 0.05)
    assert math.isclose(tiers[0]["cached"], 0.01)
    assert math.isclose(tiers[0]["output"], 0.2)
    assert tiers[1]["native"] == {
        "input": 0.2,
        "cached": 0.04,
        "output": 0.8,
    }

    # Discounted rows bill `pricing` — the catalog's pricing_rows render
    # the billed rates with the list rates as "was $" — so the billed
    # 64%-off prices convert, not the list prices.
    variant = by_id["qwen3-7-plus:variant1"]
    assert variant["rates"]["native"] == {
        "input": 0.276,
        "cached": 0.056,
        "output": 1.101,
    }
    assert [tier["contextAbove"] for tier in variant["pricingTiers"]] == [
        256_000
    ]

    # Audio-and-text output rows list with their audio capabilities.
    omni = by_id["qwen3-5-omni-flash"]
    assert omni["contextSize"] == 256_000
    assert omni["capabilities"] == {
        "reasoning": False,
        "tools": True,
        "vision": True,
        "audio": True,
    }

    # A zero price is a price: the free rows normalize to zero rates
    # instead of dropping out, and the per-request search fee (exa-search
    # bills per call) and image fee (janus-pro-deepseek bills per image)
    # stay out of the token rates.
    free = by_id["glm-4-5-flash"]
    assert free["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert free["rates"]["cachedFallback"] is False
    search = by_id["exa-search"]
    assert search["creator"] == "exa"
    assert search["contextSize"] is None
    assert search["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert search["capabilities"] == {
        "reasoning": True,
        "tools": False,
        "vision": False,
        "audio": False,
    }
    image = by_id["janus-pro-deepseek"]
    assert image["creator"] == "DeepSeek"
    assert image["rates"]["native"] == {"input": 0, "cached": 0, "output": 0}
    assert image["capabilities"]["vision"] is True

    # A row that also bills per request keeps only its token rates: the
    # $0.012-per-request fee never reaches input, cached, or output.
    sonar = by_id["perplexity-sonar"]
    assert sonar["creator"] == "perplexity"
    assert sonar["rates"]["native"] == {
        "input": 2.4,
        "cached": 2.4,
        "output": 2.4,
    }
    assert sonar["capabilities"] == {
        "reasoning": True,
        "tools": False,
        "vision": True,
        "audio": False,
    }

    # Embedding-only rows stay out: no "text" in output_modalities means
    # no token-priced listing.
    assert "text-embedding-v4" not in by_id

    assert all(
        listing["rates"]["nativeCurrency"] == "USD" for listing in listings
    )
    assert all(
        "Empirio Labs" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    zeros = _empiriolabs_rates(
        {"prompt": "0", "completion": "0", "input_cache_read": "0"}, 2.0
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # Rows without input_cache_read fall back to the input rate.
    fallback = _empiriolabs_rates(
        {"prompt": "0.000001", "completion": "0.000002"}, 2.0
    )
    assert fallback["native"] == {"input": 1.0, "cached": 1.0, "output": 2.0}
    assert fallback["cachedFallback"] is True
    # Rows without per-token prompt and completion prices are not
    # per-million-token priced and stay out of the listings.
    try:
        _empiriolabs_rates({"prompt": "0.000001"}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")


def test_engy_adapter():
    """The committed Engy catalog sample normalizes its per-token USD
    decimal strings into per-million listings converted with the ECB rate;
    the per-request and image fees stay out of the token rates."""
    # Engy's pricing page bills "$ per 1M tokens" and states "Prices are
    # live from the billing engine. The API reports the same numbers at
    # https://api.engy.ai/v1/models" (engy.ai/pricing); the registry
    # records that verified native currency, and the catalog feeds the
    # global page only.
    assert SOURCES["engy"]["nativeCurrency"] == "USD"
    assert SOURCES["engy"]["pages"] == ("global",)
    assert SOURCES["engy"]["sellerKind"] == "gateway"

    fixture = ROOT / "fixtures" / "engy-models.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    with patch("sources.engy.fetch_json", return_value=payload):
        listings = fetch_engy_listings({"usdPerEur": 2.0})
    by_id = {listing["modelId"]: listing for listing in listings}
    assert set(by_id) == {
        "deepseek-v4-flash-0731",
        "glm-5.2",
        "kimi-k3",
        "qwen3.8-27b",
    }

    # The catalog's prompt, completion, and input_cache_read fields are
    # per-token decimals (the pricing page renders "0.000000045" as
    # "$0.045" in its "$ per 1M tokens" table), so the rates scale by
    # 1,000,000 in dollars and the ECB rate converts them.
    deepseek = by_id["deepseek-v4-flash-0731"]
    assert deepseek["key"] == "engy:deepseek-v4-flash-0731"
    assert deepseek["seller"] == "engy"
    assert deepseek["sellerName"] == "Engy"
    assert deepseek["name"] == "deepseek-v4-flash-0731"
    assert deepseek["creator"] == "engy"
    assert deepseek["contextSize"] == 1_048_576
    assert deepseek["pricingTiers"] == []
    assert deepseek["rates"]["nativeCurrency"] == "USD"
    assert deepseek["rates"]["native"] == {
        "input": 0.045,
        "cached": 0.009,
        "output": 0.09,
    }
    assert math.isclose(deepseek["rates"]["input"], 0.0225)
    assert math.isclose(deepseek["rates"]["cached"], 0.0045)
    assert math.isclose(deepseek["rates"]["output"], 0.045)
    assert deepseek["rates"]["cachedFallback"] is False
    assert deepseek["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": False,
        "audio": False,
    }

    # Image-input rows carry vision capability from input_modalities.
    qwen = by_id["qwen3.8-27b"]
    assert qwen["contextSize"] == 1_001_536
    assert qwen["rates"]["native"] == {
        "input": 0.045,
        "cached": 0.015,
        "output": 0.32,
    }
    assert qwen["capabilities"] == {
        "reasoning": False,
        "tools": False,
        "vision": True,
        "audio": False,
    }

    kimi = by_id["kimi-k3"]
    assert kimi["rates"]["native"] == {
        "input": 1.95,
        "cached": 0.195,
        "output": 9.75,
    }
    assert math.isclose(kimi["rates"]["input"], 0.975)
    assert math.isclose(kimi["rates"]["cached"], 0.0975)
    assert math.isclose(kimi["rates"]["output"], 4.875)
    assert kimi["capabilities"]["vision"] is True

    glm = by_id["glm-5.2"]
    assert glm["contextSize"] == 262_144
    assert glm["rates"]["native"] == {
        "input": 0.68,
        "cached": 0.18,
        "output": 1.5,
    }

    assert all(listing["rates"]["nativeCurrency"] == "USD" for listing in listings)
    assert all(
        "Engy" in listing["priceNote"] and "ECB" in listing["priceNote"]
        for listing in listings
    )
    # A zero price is a price: zero token rows normalize to zero rates
    # instead of dropping out.
    zeros = _engy_rates(
        {"prompt": "0", "completion": "0", "input_cache_read": "0"}, 2.0
    )
    assert zeros["input"] == zeros["cached"] == zeros["output"] == 0
    assert zeros["nativeCurrency"] == "USD"
    assert zeros["cachedFallback"] is False
    # The per-request and image fees stay out of the token rates.
    assert "request" not in deepseek["rates"]["native"]
    assert "image" not in deepseek["rates"]["native"]
    # Rows without input_cache_read fall back to the input rate.
    fallback = _engy_rates({"prompt": "0.000001", "completion": "0.000002"}, 2.0)
    assert fallback["native"] == {"input": 1.0, "cached": 1.0, "output": 2.0}
    assert fallback["cachedFallback"] is True
    # Rows without per-token prompt and completion prices are not
    # per-million-token priced and stay out of the listings.
    try:
        _engy_rates({"prompt": "0.000001"}, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("missing per-token prices should skip the row")


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
    """Patch the build's ECB fetch and every registered listings adapter.
    Values are return values for `ok`, exceptions for failing sources."""
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
    # Eden AI's endpoint view lists one row per selling provider, so its
    # catalog is the site's biggest; Requesty's is the next biggest and
    # OpenRouter's the biggest of the routers.
    assert counts["edenai"] == max(counts.values())
    assert counts["edenai"] > 1000
    assert counts["requesty"] > 400
    assert counts["nano-gpt"] > 600
    assert counts["empiriolabs"] > 100
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
    assert native_by_seller["novita"] == "USD"
    assert native_by_seller["requesty"] == "USD"
    assert native_by_seller["nano-gpt"] == "USD"
    assert native_by_seller["vercel-gateway"] == "USD"
    assert native_by_seller["kilo"] == "USD"
    assert native_by_seller["chutes"] == "USD"
    assert native_by_seller["llmgateway"] == "USD"
    assert native_by_seller["aiand"] == "USD"
    assert native_by_seller["aimlapi"] == "USD"
    assert native_by_seller["ambient"] == "USD"
    assert native_by_seller["crossmodel"] == "USD"
    assert native_by_seller["edenai"] == "USD"
    assert native_by_seller["empiriolabs"] == "USD"
    assert native_by_seller["engy"] == "USD"
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
        'data-seller="novita"',
        'data-seller="requesty"',
        'data-seller="nano-gpt"',
        'data-seller="vercel-gateway"',
        'data-seller="kilo"',
        'data-seller="chutes"',
        'data-seller="llmgateway"',
        'data-seller="aiand"',
        'data-seller="aimlapi"',
        'data-seller="ambient"',
        'data-seller="crossmodel"',
        'data-seller="edenai"',
        'data-seller="empiriolabs"',
        'data-seller="engy"',
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
    test_novita_adapter()
    test_requesty_adapter()
    test_nano_gpt_adapter()
    test_vercel_gateway_adapter()
    test_kilo_adapter()
    test_chutes_adapter()
    test_llm_gateway_adapter()
    test_aiand_adapter()
    test_aimlapi_adapter()
    test_ambient_adapter()
    test_crossmodel_adapter()
    test_edenai_adapter()
    test_empiriolabs_adapter()
    test_engy_adapter()
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
