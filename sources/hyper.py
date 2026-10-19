"""Hyper adapter: USD catalog prices from Hyper's keyless model catalog,
converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _is_text_output,
    _rates,
    fetch_json,
    listing_from_offer,
)

HYPER_URL = "https://hyper.charm.land/v1/models"


def _hyper_rates(model: dict, usd_per_eur: float) -> dict:
    # Hyper's List Models doc documents the catalog's `pricing` field as
    # "Per-million-token pricing", and its credits doc points at the
    # /v1/models endpoint "for per-model pricing in dollars per million
    # tokens", so the rates pass through unmultiplied in dollars and the
    # ECB rate converts them. `cache_hit` is the cached-input read price
    # ("Cost per 1M tokens read from the prompt cache"); the zero-priced
    # `cache_create` write field never stands in for it, and a missing
    # cache_hit falls back to the input rate.
    pricing = model.get("pricing") or {}
    native = _rates(
        pricing.get("input"),
        pricing.get("output"),
        pricing.get("cache_hit"),
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


def _hyper_capabilities(model: dict) -> dict:
    # The catalog flags vision under `capabilities.vision` and reasoning
    # through a `reasoning` effort-levels block; no tool-use or audio
    # flags are published.
    return {
        "reasoning": bool(model.get("reasoning")),
        "tools": False,  # the catalog publishes no tool-use flag
        "vision": bool((model.get("capabilities") or {}).get("vision")),
        "audio": False,
    }


def _hyper_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"hyper:{model['id']}",
        "router": "hyper",
        "routerName": "Hyper",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _creator(model.get("producer")),
        "description": "",
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _hyper_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Hyper's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_hyper_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Hyper's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_hyper(exchange_rate)]


def fetch_hyper(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(HYPER_URL), "Hyper")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _hyper_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_hyper_offer(model, default))
    if not offers:
        raise ValueError("Hyper has no usable token-priced offers")
    return offers
