"""nano-gpt adapter: USD catalog prices from nano-gpt's keyless detailed
model catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _converted_usd_rates,
    _creator,
    _number,
    fetch_json,
    listing_from_offer,
)

# The basic /v1/models catalog carries no prices; only the detailed one
# publishes per-model pricing.
NANO_GPT_URL = "https://nano-gpt.com/api/v1/models?detailed=true"


def _nano_gpt_rates(model: dict, usd_per_eur: float) -> dict:
    # nano-gpt's own pricing page bills text API usage "at the model's list
    # price ... per million tokens" in USD, and every catalog row prices
    # `unit: "per_million_tokens"`, so prompt and completion pass through
    # unmultiplied. The cache-read field is quoted per 1,000 tokens
    # (cacheReadInputPer1kTokens) and scales by 1,000; the separate
    # cache-write field is not a cached-input read. A missing cache-read
    # rate falls back to the input rate; zero prices are kept.
    pricing = model.get("pricing") or {}
    cache_read = pricing.get("cacheReadInputPer1kTokens")
    return _converted_usd_rates(
        {
            "input": pricing.get("prompt"),
            "cache_read": (
                _number(cache_read, "cacheReadInputPer1kTokens") * 1_000
                if cache_read is not None
                else None
            ),
            "output": pricing.get("completion"),
        },
        usd_per_eur,
    )


def _nano_gpt_capabilities(model: dict) -> dict:
    flags = model.get("capabilities") or {}
    return {
        "reasoning": bool(flags.get("reasoning")),
        "tools": bool(flags.get("tool_calling")),
        "vision": bool(flags.get("vision")),
        "audio": bool(flags.get("audio_input")),
    }


def _nano_gpt_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"nano-gpt:{model['id']}",
        "router": "nano-gpt",
        "routerName": "nano-gpt",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_length"),
        "capabilities": _nano_gpt_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in nano-gpt's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_nano_gpt_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: nano-gpt's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_nano_gpt(exchange_rate)]


def fetch_nano_gpt(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(NANO_GPT_URL), "nano-gpt")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _nano_gpt_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without prompt and completion prices (the catalog's
            # varies_by_modality rows) are not per-million-token priced.
            continue
        offers.append(_nano_gpt_offer(model, default))
    if not offers:
        raise ValueError("nano-gpt has no usable token-priced offers")
    return offers
