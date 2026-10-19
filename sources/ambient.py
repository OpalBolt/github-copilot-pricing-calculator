"""Ambient adapter: USD catalog prices from Ambient's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _rates,
    fetch_json,
    listing_from_offer,
)

AMBIENT_URL = "https://api.ambient.xyz/v1/models"


def _ambient_per_million(per_token, label: str) -> float:
    # Each catalog row pairs its per-million floats with per-token decimals
    # (input 0.6 for prompt "0.0000006"), and input_cache_read publishes
    # only the per-token decimal, so it scales by 1,000,000 like its
    # prompt/completion siblings.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _ambient_rates(model: dict, usd_per_eur: float) -> dict:
    # Ambient's docs publish the catalog's per-model prices "as USD per
    # million tokens (pricing.input and pricing.output)" (ambient.xyz/docs/
    # build/models), so input and output pass through unmultiplied; a
    # missing input_cache_read falls back to the input rate and zero prices
    # are kept.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_read")
    native = _rates(
        pricing.get("input"),
        pricing.get("output"),
        (
            _ambient_per_million(cached, "input_cache_read")
            if cached is not None
            else None
        ),
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


def _ambient_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"ambient:{model['id']}",
        "router": "ambient",
        "routerName": "Ambient",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        # The catalog's owned_by names Ambient for most rows, so the
        # creator comes from the id's vendor prefix (z-ai/glm-5.2).
        "owner": _creator(
            model["id"].split("/", 1)[0] if "/" in model["id"] else ""
        ),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_length"),
        "capabilities": _capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Ambient's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_ambient_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Ambient's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_ambient(exchange_rate)]


def fetch_ambient(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(AMBIENT_URL), "Ambient")
    offers = []
    for model in models:
        # is_ready is a routing flag consumed by OpenRouter, "not a
        # served/not-served signal" (ambient.xyz/docs/build/models), so it
        # gates nothing here either.
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _ambient_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-million input and output prices are not
            # per-million-token priced and skip the row.
            continue
        offers.append(_ambient_offer(model, default))
    if not offers:
        raise ValueError("Ambient has no usable token-priced offers")
    return offers
