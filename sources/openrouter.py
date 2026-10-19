"""OpenRouter adapter: USD router prices converted with the ECB rate."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _usd_rates,
    fetch_json,
    listing_from_offer,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_EU_URL = "https://eu.openrouter.ai/api/v1/models"


def _openrouter_rates(model: dict, usd_per_eur: float) -> dict:
    return _usd_rates(model, usd_per_eur)


def fetch_openrouter_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: OpenRouter's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(
            offer,
            price_note=(
                "USD price published in OpenRouter's model catalog and "
                "converted with the listed ECB rate."
            ),
        )
        for offer in fetch_openrouter(exchange_rate)
    ]


def fetch_openrouter(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(OPENROUTER_URL), "OpenRouter")
    eu_models = {
        model["id"]: model
        for model in _catalog(fetch_json(OPENROUTER_EU_URL), "OpenRouter EU")
        if model.get("id")
    }
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _openrouter_rates(model, exchange_rate["usdPerEur"])
            eu_model = eu_models.get(model["id"])
            eu = _openrouter_rates(eu_model, exchange_rate["usdPerEur"]) if eu_model else None
        except ValueError:
            continue
        offers.append(
            {
                "key": f"openrouter:{model['id']}",
                "router": "openrouter",
                "routerName": "OpenRouter",
                "modelId": model["id"],
                "name": model.get("name") or model["id"],
                "owner": _creator(
                    model["id"].split("/", 1)[0] if "/" in model["id"] else ""
                ),
                "description": model.get("description", ""),
                "releaseDate": model.get("release_date"),
                "contextSize": model.get("context_length"),
                "capabilities": _capabilities(model),
                "providers": [],
                "euProviders": [],
                "default": default,
                "eu": eu,
                "quantization": None,
                "euPlan": "Business or Enterprise",
                "priceNote": "USD Router Price converted with the listed ECB rate.",
            }
        )
    if not offers:
        raise ValueError("OpenRouter has no usable text-output offers")
    return offers
