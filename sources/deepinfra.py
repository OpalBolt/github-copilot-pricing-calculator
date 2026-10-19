"""DeepInfra adapter: USD catalog prices from DeepInfra's keyless model
catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

DEEPINFRA_URL = "https://api.deepinfra.com/v1/models"


def _deepinfra_pricing(model: dict) -> dict:
    return (model.get("metadata") or {}).get("pricing") or {}


def _deepinfra_rates(pricing: dict, usd_per_eur: float) -> dict:
    # DeepInfra's `*_tokens` prices are already dollars per 1M tokens (the
    # "$ per 1M input tokens" columns on its pricing page), so no per-token
    # multiplication; `cache_read_tokens` is absent from catalogs without
    # published cache prices and falls back to the input rate.
    native = _rates(
        pricing.get("input_tokens"),
        pricing.get("output_tokens"),
        pricing.get("cache_read_tokens"),
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


def _deepinfra_capabilities(model: dict) -> dict:
    tags = {
        str(tag).lower()
        for tag in (model.get("metadata") or {}).get("tags") or []
    }
    return {
        "reasoning": "reasoning" in tags,
        "tools": False,  # the catalog publishes no tool-use tag
        "vision": bool({"vlm", "vision"} & tags),
        "audio": bool({"tts", "stt"} & tags),
    }


def _deepinfra_offer(model: dict, default: dict) -> dict:
    metadata = model.get("metadata") or {}
    return {
        "key": f"deepinfra:{model['id']}",
        "router": "deepinfra",
        "routerName": "DeepInfra",
        "modelId": model["id"],
        "name": model["id"],
        "owner": _creator(
            model["id"].split("/", 1)[0] if "/" in model["id"] else ""
        ),
        "description": metadata.get("description", ""),
        "releaseDate": None,
        "contextSize": metadata.get("context_length"),
        "capabilities": _deepinfra_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in DeepInfra's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_deepinfra_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: DeepInfra's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_deepinfra(exchange_rate)]


def fetch_deepinfra(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(DEEPINFRA_URL), "DeepInfra")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _deepinfra_rates(
                _deepinfra_pricing(model), exchange_rate["usdPerEur"]
            )
        except ValueError:
            # Rows without per-token input and output prices (embeddings,
            # image, TTS, ASR, video) are not per-million-token priced.
            continue
        offers.append(_deepinfra_offer(model, default))
    if not offers:
        raise ValueError("DeepInfra has no usable token-priced offers")
    return offers
