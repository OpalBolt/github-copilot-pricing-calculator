"""Kilo adapter: USD catalog prices from Kilo's keyless gateway model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

KILO_URL = "https://api.kilo.ai/api/gateway/models"


def _kilo_per_million(per_token, label: str) -> float:
    # Kilo's Usage & Billing doc derives costs from "the upstream
    # provider's pricing based on token usage" and bills with "microdollar
    # precision (1 USD = 1,000,000 microdollars)", so the catalog's
    # per-token decimals scale by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _kilo_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog prices input (prompt), output (completion), and
    # input_cache_read per token in USD; a missing input_cache_read falls
    # back to the input rate and zero prices are kept. The auto-routing
    # rows' -1 sentinel is negative and skips the row.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_read")
    native = _rates(
        _kilo_per_million(pricing.get("prompt"), "prompt"),
        _kilo_per_million(pricing.get("completion"), "completion"),
        (
            _kilo_per_million(cached, "input_cache_read")
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


def _kilo_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"kilo:{model['id']}",
        "router": "kilo",
        "routerName": "Kilo",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        # The catalog publishes no owned_by field; the id's vendor prefix
        # ("anthropic/claude-sonnet-4.5") is the creator.
        "owner": _creator(model["id"].split("/", 1)[0]),
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
            "USD price published in Kilo's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_kilo_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Kilo's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_kilo(exchange_rate)]


def fetch_kilo(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(KILO_URL), "Kilo")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _kilo_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token prompt and completion prices (the
            # auto-routing rows' -1 sentinel) are not token-priced.
            continue
        offers.append(_kilo_offer(model, default))
    if not offers:
        raise ValueError("Kilo has no usable token-priced offers")
    return offers
