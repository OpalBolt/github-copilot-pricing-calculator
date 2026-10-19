"""Vercel AI Gateway adapter: USD catalog prices from Vercel's keyless model
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

VERCEL_GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/models"


def _vercel_gateway_per_million(per_token, label: str) -> float:
    # Vercel's AI Gateway Model List renders the catalog's price fields as
    # dollars per 1M tokens (inputCost 0.12 for the catalog's "0.00000012"),
    # so the per-token prices scale by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _vercel_gateway_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog prices input, output, and input_cache_read per token in
    # USD; a missing input_cache_read falls back to the input rate and zero
    # prices are kept.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_read")
    native = _rates(
        _vercel_gateway_per_million(pricing.get("input"), "input"),
        _vercel_gateway_per_million(pricing.get("output"), "output"),
        (
            _vercel_gateway_per_million(cached, "input_cache_read")
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


def _vercel_gateway_is_text_output(model: dict) -> bool:
    # The catalog nests modalities as {"input": [...], "output": [...]}.
    outputs = (model.get("modalities") or {}).get("output") or ["text"]
    return "text" in {str(value).lower() for value in outputs}


def _vercel_gateway_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"vercel-gateway:{model['id']}",
        "router": "vercel-gateway",
        "routerName": "Vercel AI Gateway",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Vercel AI Gateway's model catalog and "
            "converted with the listed ECB rate."
        ),
    }


def fetch_vercel_gateway_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Vercel AI Gateway's catalog prices,
    re-noted as listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(offer)
        for offer in fetch_vercel_gateway(exchange_rate)
    ]


def fetch_vercel_gateway(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(VERCEL_GATEWAY_URL), "Vercel AI Gateway")
    offers = []
    for model in models:
        if not model.get("id") or not _vercel_gateway_is_text_output(model):
            continue
        try:
            default = _vercel_gateway_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices (embeddings,
            # image, video, rerank) are not per-million-token priced.
            continue
        offers.append(_vercel_gateway_offer(model, default))
    if not offers:
        raise ValueError("Vercel AI Gateway has no usable token-priced offers")
    return offers
