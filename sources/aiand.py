"""aiand adapter: USD catalog prices from ai&'s keyless model catalog,
converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

AIAND_URL = "https://api.aiand.com/v1/models"


def _aiand_rates(model: dict, usd_per_eur: float) -> dict:
    # ai&'s pricing doc bills "(input_tokens / 1_000_000) × input_per_1m",
    # so the catalog's input_per_1m, output_per_1m, and
    # cached_input_per_1m fields are already dollars per 1M tokens and
    # pass through unmultiplied; a missing cached_input_per_1m falls back
    # to the input rate and zero prices are kept.
    native = _rates(
        model.get("input_per_1m"),
        model.get("output_per_1m"),
        model.get("cached_input_per_1m"),
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


def _aiand_capabilities(model: dict) -> dict:
    # The catalog's capabilities field lists the documented feature values
    # ("reasoning", "tool_calling", "vision", "video", "document");
    # vision, video, and document inputs all map to the vision capability.
    features = {str(value).lower() for value in (model.get("capabilities") or [])}
    return {
        "reasoning": "reasoning" in features,
        "tools": "tool_calling" in features,
        "vision": bool({"vision", "video", "document"} & features),
        "audio": "audio" in features,
    }


def _aiand_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"aiand:{model['id']}",
        "router": "aiand",
        "routerName": "aiand",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        # The catalog's provider field names "the lab that released the
        # open weights" (docs.aiand.com/models/catalog); owned_by is
        # always the seller itself ("ai&").
        "owner": _creator(model.get("provider")),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _aiand_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in aiand's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_aiand_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: aiand's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_aiand(exchange_rate)]


def fetch_aiand(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(AIAND_URL), "aiand")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _aiand_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-million input and output prices are not
            # per-million-token priced and skip the row.
            continue
        offers.append(_aiand_offer(model, default))
    if not offers:
        raise ValueError("aiand has no usable token-priced offers")
    return offers
