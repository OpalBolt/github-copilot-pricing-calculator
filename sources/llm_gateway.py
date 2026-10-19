"""LLM Gateway adapter: USD catalog prices from LLM Gateway's keyless model
catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _per_million_rates,
    fetch_json,
    listing_from_offer,
)

LLM_GATEWAY_URL = "https://api.llmgateway.io/v1/models"


def _llm_gateway_rates(model: dict, usd_per_eur: float) -> dict:
    # LLM Gateway's model directory renders the catalog's price fields as
    # dollars per 1M tokens ("Input $0.15 /M tokens Cache Read $0.075 /M
    # tokens Output $0.6 /M tokens" for gpt-4o-mini, whose row prices
    # prompt "0.15e-6"), so the per-token decimals scale by 1,000,000 in
    # dollars and the ECB rate converts them; a published zero cache-read
    # price stays a price and missing prices fall back to the input rate.
    native = _per_million_rates(
        model.get("pricing") or {}, native_currency="USD"
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


def _llm_gateway_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"llmgateway:{model['id']}",
        "router": "llmgateway",
        "routerName": "LLM Gateway",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        # The catalog's family field names the creator ("openai",
        # "moonshot", "deepseek"); the description only lists the serving
        # providers ("provided by openai, azure").
        "owner": _creator(model.get("family")),
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
            "USD price published in LLM Gateway's model catalog and "
            "converted with the listed ECB rate."
        ),
    }


def fetch_llmgateway_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: LLM Gateway's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(offer) for offer in fetch_llmgateway(exchange_rate)
    ]


def fetch_llmgateway(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(LLM_GATEWAY_URL), "LLM Gateway")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _llm_gateway_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token prompt and completion prices are not
            # per-million-token priced and skip the row.
            continue
        offers.append(_llm_gateway_offer(model, default))
    if not offers:
        raise ValueError("LLM Gateway has no usable token-priced offers")
    return offers
