"""Chutes adapter: USD catalog prices from Chutes' keyless model catalog,
converted with the listed ECB rate."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

CHUTES_URL = "https://llm.chutes.ai/v1/models"


def _chutes_rates(model: dict, usd_per_eur: float) -> dict:
    # Chutes's pricing page charges "per million tokens, separately for
    # input and output" and quotes the catalog rows as dollars per 1M
    # tokens ($0.12 per 1M tokens for the row whose pricing.prompt is 0.12),
    # so the prompt, completion, and input_cache_read fields pass through
    # unmultiplied; a missing input_cache_read falls back to the input rate
    # and zero prices are kept.
    pricing = model.get("pricing") or {}
    native = _rates(
        pricing.get("prompt"),
        pricing.get("completion"),
        pricing.get("input_cache_read"),
        native_currency="USD",
    )
    converted = {
        key: value / usd_per_eur
        for key, value in native.items()
        if key in {"input", "cached", "output"}
    }
    return {
        **converted,
        "cachedFallback": native["cachedFallback"],
        "nativeCurrency": "USD",
        "native": {
            field: native[field] for field in ("input", "cached", "output")
        },
    }


def _chutes_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"chutes:{model['id']}",
        "router": "chutes",
        "routerName": "Chutes",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        # The catalog's owned_by field names the serving engine (sglang,
        # vllm), not the creator; the id's vendor prefix
        # ("deepseek-ai/DeepSeek-V3.2-TEE") is the creator.
        "owner": _creator(
            model["id"].split("/", 1)[0] if "/" in model["id"] else ""
        ),
        "description": model.get("description", ""),
        "releaseDate": None,
        # The pricing page's Context column reads context_length and falls
        # back to max_model_len when the catalog leaves it null.
        "contextSize": model.get("context_length") or model.get("max_model_len"),
        "capabilities": _capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in the Chutes model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_chutes_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Chutes' catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_chutes(exchange_rate)]


def fetch_chutes(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(CHUTES_URL), "Chutes")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _chutes_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-million-token prompt and completion prices
            # are not token-priced and skip the row.
            continue
        offers.append(_chutes_offer(model, default))
    if not offers:
        raise ValueError("Chutes has no usable token-priced offers")
    return offers
