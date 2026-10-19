"""Engy adapter: USD catalog prices from Engy's keyless model catalog,
converted with the listed ECB rate."""

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

ENGY_URL = "https://api.engy.ai/v1/models"


def _engy_per_million(per_token, label: str) -> float:
    # Engy prices per token: the catalog's "0.000000045" prompt decimal is
    # rendered on engy.ai/pricing as "$0.045" in its "$ per 1M tokens"
    # table, so per-million rates scale the decimals by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _engy_rates(pricing: dict, usd_per_eur: float) -> dict:
    # The catalog prices prompt, completion, and input_cache_read as
    # per-token decimals in USD; the `request` field prices per-call
    # features and `image` prices images, so neither feeds the token
    # rates. A missing input_cache_read falls back to the input rate; zero
    # prices are kept.
    cached = pricing.get("input_cache_read")
    native = _rates(
        _engy_per_million(pricing.get("prompt"), "input"),
        _engy_per_million(pricing.get("completion"), "output"),
        (
            _engy_per_million(cached, "input_cache_read")
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


def _engy_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"engy:{model['id']}",
        "router": "engy",
        "routerName": "Engy",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(model.get("owned_by")),
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
            "USD price published in Engy's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_engy_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Engy's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_engy(exchange_rate)]


def fetch_engy(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(ENGY_URL), "Engy")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _engy_rates(
                model.get("pricing") or {}, exchange_rate["usdPerEur"]
            )
        except ValueError:
            # Rows without per-token prompt and completion prices are not
            # per-million-token priced.
            continue
        offers.append(_engy_offer(model, default))
    if not offers:
        raise ValueError("Engy has no usable token-priced offers")
    return offers
