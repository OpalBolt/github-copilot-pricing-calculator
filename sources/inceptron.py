"""Inceptron adapter: USD catalog prices from Inceptron's keyless model
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

INCEPTRON_URL = "https://api.inceptron.io/v1/models"


def _inceptron_per_million(per_token, label: str) -> float:
    # Inceptron's models page renders the catalog's price fields as dollars
    # per 1M tokens ("Input tokens, 1M $1.40", "Cache read $0.26" for
    # GLM-5.3), so the per-token decimals scale by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _inceptron_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog prices input, output, and cached input per token in USD
    # under `prompt`, `completion`, and `input_cache_reads`; the zero-priced
    # `input_cache_writes` write field never stands in for the read, and a
    # missing `input_cache_reads` falls back to the input rate.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_reads")
    native = _rates(
        _inceptron_per_million(pricing.get("prompt"), "input"),
        _inceptron_per_million(pricing.get("completion"), "output"),
        (
            _inceptron_per_million(cached, "input_cache_reads")
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


def _inceptron_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"inceptron:{model['id']}",
        "router": "inceptron",
        "routerName": "Inceptron",
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
            "USD price published in Inceptron's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_inceptron_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Inceptron's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(offer) for offer in fetch_inceptron(exchange_rate)
    ]


def fetch_inceptron(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(INCEPTRON_URL), "Inceptron")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _inceptron_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices (image, audio,
            # per-request billing) are not per-million-token priced.
            continue
        offers.append(_inceptron_offer(model, default))
    if not offers:
        raise ValueError("Inceptron has no usable token-priced offers")
    return offers
