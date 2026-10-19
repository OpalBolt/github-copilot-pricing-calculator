"""Novita adapter: USD catalog prices from Novita's keyless model catalog,
converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _converted_usd_rates,
    _creator,
    _number,
    fetch_json,
    listing_from_offer,
)

NOVITA_URL = "https://api.novita.ai/v3/openai/models"


def _novita_price(component: dict) -> float:
    # The "$ per Mt" quotes on novita.ai/pricing are the
    # `price_per_m_decimal` values; the integer `price_per_m` is the same
    # price in 1/10000 currency units per 1M tokens.
    decimal = component.get("price_per_m_decimal")
    if decimal is not None:
        return _number(decimal, "price_per_m_decimal")
    return _number(component.get("price_per_m"), "price_per_m") / 10_000


def _novita_component(pricing: dict, key: str):
    component = pricing.get(key)
    return _novita_price(component) if isinstance(component, dict) else None


def _novita_rates(pricing: dict, usd_per_eur: float) -> dict:
    # Novita's price components are already currency units per 1M tokens,
    # so they pass through unmultiplied and convert with the listed ECB
    # rate; a missing input_cache_read component falls back to the input
    # rate.
    return _converted_usd_rates(
        {
            "input": _novita_component(pricing, "prompt"),
            "cache_read": _novita_component(pricing, "input_cache_read"),
            "output": _novita_component(pricing, "completion"),
        },
        usd_per_eur,
    )


def _novita_capabilities(model: dict) -> dict:
    features = {
        str(feature).lower() for feature in model.get("features") or []
    }
    inputs = {
        str(modality).lower()
        for modality in model.get("input_modalities") or []
    }
    return {
        "reasoning": "reasoning" in features,
        "tools": "function-calling" in features,
        "vision": bool({"image", "video"} & inputs),
        "audio": "audio" in inputs,
    }


def _novita_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"novita:{model['id']}",
        "router": "novita",
        "routerName": "Novita",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _creator(model["id"].split("/", 1)[0]),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_size"),
        "capabilities": _novita_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Novita's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_novita_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Novita's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_novita(exchange_rate)]


def fetch_novita(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(NOVITA_URL), "Novita")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _novita_rates(
                model.get("pricing") or {}, exchange_rate["usdPerEur"]
            )
        except ValueError:
            # Rows without prompt and completion prices are not
            # per-million-token priced.
            continue
        offers.append(_novita_offer(model, default))
    if not offers:
        raise ValueError("Novita has no usable token-priced offers")
    return offers
