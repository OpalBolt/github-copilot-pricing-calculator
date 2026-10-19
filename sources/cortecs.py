"""Cortecs adapter: model-level EUR prices from the Cortecs catalogs."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _provider,
    _rates,
    fetch_json,
    listing_from_offer,
)

CORTECS_URL = "https://api.cortecs.ai/v1/models?extended=true&currency=EUR"
CORTECS_EU_URL = CORTECS_URL + "&eu_native=true"


def _heavy_quantization(model: dict, rates: dict) -> str | None:
    for details in model.get("providers_details", {}).values():
        pricing = details.get("pricing", {})
        if (
            pricing.get("input_token") == rates["input"]
            and pricing.get("output_token") == rates["output"]
            and pricing.get("cache_read_cost") == (
                None if rates["cachedFallback"] else rates["cached"]
            )
            and str(details.get("quantization", "")).lower() in {"fp4", "int4"}
        ):
            return str(details["quantization"]).lower()
    return None


def _cortecs_offer(model: dict, eu_model: dict | None) -> dict:
    pricing = model.get("pricing", {})
    default = _rates(
        pricing.get("input_token"),
        pricing.get("output_token"),
        pricing.get("cache_read_cost"),
    )
    eu = None
    eu_providers = []
    if eu_model:
        eu_pricing = eu_model.get("pricing", {})
        eu = _rates(
            eu_pricing.get("input_token"),
            eu_pricing.get("output_token"),
            eu_pricing.get("cache_read_cost"),
        )
        eu_providers = [_provider(name) for name in eu_model.get("providers", [])]
    return {
        "key": f"cortecs:{model['id']}",
        "router": "cortecs",
        "routerName": "Cortecs",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description", ""),
        "releaseDate": model.get("release_date"),
        "contextSize": model.get("context_size"),
        "capabilities": _capabilities(model),
        "providers": [_provider(name) for name in model.get("providers", [])],
        "euProviders": eu_providers,
        "default": default,
        "eu": eu,
        "quantization": _heavy_quantization(model, default),
        "priceNote": "Model-level minimum price published by Cortecs.",
    }


def fetch_cortecs_listings() -> list[dict]:
    """Global-page Model Listings: Cortecs' model-level minimum prices.
    The router offers are already listing-shaped, so only the EU-page fields
    are stripped."""
    return [listing_from_offer(offer) for offer in fetch_cortecs()]


def fetch_cortecs() -> list[dict]:
    models = _catalog(fetch_json(CORTECS_URL), "Cortecs")
    eu_models = {
        model["id"]: model
        for model in _catalog(fetch_json(CORTECS_EU_URL), "Cortecs EU")
        if model.get("id")
    }
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        offers.append(_cortecs_offer(model, eu_models.get(model["id"])))
    if not offers:
        raise ValueError("Cortecs has no usable text-output offers")
    return offers
