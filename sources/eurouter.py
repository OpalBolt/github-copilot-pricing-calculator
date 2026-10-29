"""EUrouter adapter: EUR and USD router prices from the EUrouter catalog."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _per_million_rates,
    _provider,
    _usd_rates,
    fetch_json,
    listing_from_offer,
)

EUROUTER_URL = "https://api.eurouter.ai/api/v1/models"


def _eurouter_listing_note(offer: dict) -> str:
    if offer["default"]["nativeCurrency"] == "EUR":
        return "EUR price published in EUrouter's catalog."
    return (
        "USD price published in EUrouter's catalog and converted with the "
        "listed ECB rate."
    )


def fetch_eurouter_listings(exchange_rate: dict | None = None) -> list[dict]:
    """Global-page Model Listings: EUrouter's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(offer, price_note=_eurouter_listing_note(offer))
        for offer in fetch_eurouter(exchange_rate)
    ]


def fetch_eurouter(exchange_rate: dict | None = None) -> list[dict]:
    models = _catalog(fetch_json(EUROUTER_URL), "EUrouter")
    offers = []
    for model in models:
        endpoints = set(model.get("supported_api_endpoints") or [])
        pricing = model.get("pricing", {})
        currency = pricing.get("currency")
        if (
            not model.get("id")
            or not _is_text_output(model)
            or "chat.completions" not in endpoints
            or currency not in {"EUR", "USD"}
            or (currency == "USD" and not exchange_rate)
        ):
            continue
        try:
            rates = (
                _per_million_rates(pricing, native_currency="EUR")
                if currency == "EUR"
                else _usd_rates(model, exchange_rate["usdPerEur"])
            )
        except ValueError:
            continue
        providers = model.get("providers") or []
        if providers and isinstance(providers[0], dict):
            providers = [
                provider.get("name") or provider.get("id")
                for provider in providers
                if provider.get("name") or provider.get("id")
            ]
        providers = [_provider(name) for name in providers]
        offer = {
            "key": f"eurouter:{model['id']}",
            "router": "eurouter",
            "routerName": "EUrouter",
            "modelId": model["id"],
            "name": model.get("name") or model["id"],
            "owner": _creator(
                (model.get("author_info") or {}).get("display_name")
                or model.get("author")
                or model.get("owned_by")
                or ""
            ),
            "description": model.get("description", ""),
            "releaseDate": model.get("release_date"),
            "contextSize": model.get("context_size") or model.get("context_length"),
            "capabilities": _capabilities(model),
            "providers": providers,
            "euProviders": providers,
            "default": rates,
            "eu": dict(rates),
            "quantization": None,
            "priceNote": (
                "EUR Router Price published by EUrouter."
                if currency == "EUR"
                else "USD Router Price published by EUrouter and converted with the listed ECB rate."
            ),
        }
        offers.append(offer)
    if not offers:
        raise ValueError("EUrouter has no usable text-output offers")
    return offers
