"""Pioneer (Fastino) adapter: USD catalog prices from Fastino's keyless model
catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

PIONEER_URL = "https://api.fastino.ai/v1/models"


def _pioneer_rates(model: dict, usd_per_eur: float) -> dict:
    # Fastino's pricing page states "Token prices are USD per 1M tokens"
    # (docs.fastino.ai/pricing) and repeats the catalog's values in its
    # inference table ($0.08 input / $0.45 output for Nemotron 3.5 Super VL,
    # the catalog's input_price_per_million 0.08 and
    # output_price_per_million 0.45), so the per-million fields pass through
    # unmultiplied; a missing cache_read_price_per_million falls back to the
    # input rate and zero prices are kept.
    native = _rates(
        model.get("input_price_per_million"),
        model.get("output_price_per_million"),
        model.get("cache_read_price_per_million"),
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


def _pioneer_capabilities(model: dict) -> dict:
    # The catalog nests capability flags as {"supported": bool} dicts
    # (thinking, image_input, ...); it publishes no tool or audio flag.
    flags = model.get("capabilities") or {}
    return {
        "reasoning": bool((flags.get("thinking") or {}).get("supported")),
        "tools": False,
        "vision": bool((flags.get("image_input") or {}).get("supported")),
        "audio": False,
    }


def _pioneer_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"pioneer:{model['id']}",
        "router": "pioneer",
        "routerName": "Pioneer (Fastino)",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("max_input_tokens"),
        "capabilities": _pioneer_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Fastino's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_pioneer_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Fastino's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_pioneer(exchange_rate)]


def fetch_pioneer(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(PIONEER_URL), "Pioneer (Fastino)")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _pioneer_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-million input and output prices are not
            # token-priced and skip the row.
            continue
        offers.append(_pioneer_offer(model, default))
    if not offers:
        raise ValueError("Pioneer (Fastino) has no usable token-priced offers")
    return offers
