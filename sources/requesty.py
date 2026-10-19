"""Requesty adapter: USD catalog prices from Requesty's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

REQUESTY_URL = "https://router.requesty.ai/v1/models"


def _requesty_per_million(per_token, label: str) -> float:
    # Requesty's API reference documents the catalog's price fields as
    # per-token USD prices ("Price per input token in USD",
    # docs.requesty.ai), so per-million rates scale them by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _requesty_rates(model: dict, usd_per_eur: float) -> dict:
    # The published prices are what the buyer pays: rows with a
    # discount_percentage already quote the discounted price. A missing
    # cached_price falls back to the input rate; zero prices are kept.
    native = _rates(
        _requesty_per_million(model.get("input_price"), "input_price"),
        _requesty_per_million(model.get("output_price"), "output_price"),
        (
            _requesty_per_million(model["cached_price"], "cached_price")
            if model.get("cached_price") is not None
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


def _requesty_capabilities(model: dict) -> dict:
    return {
        "reasoning": bool(model.get("supports_reasoning")),
        "tools": bool(model.get("supports_tool_calling")),
        "vision": bool(model.get("supports_vision")),
        "audio": False,  # the catalog publishes no audio modality flag
    }


def _requesty_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"requesty:{model['id']}",
        "router": "requesty",
        "routerName": "Requesty",
        "modelId": model["id"],
        "name": model.get("model_canonical_name") or model["id"],
        "owner": _creator(model.get("model_lab")),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _requesty_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Requesty's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_requesty_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Requesty's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_requesty(exchange_rate)]


def fetch_requesty(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(REQUESTY_URL), "Requesty")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _requesty_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_requesty_offer(model, default))
    if not offers:
        raise ValueError("Requesty has no usable token-priced offers")
    return offers
