"""Eden AI adapter: USD catalog prices from Eden AI's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

EDENAI_URL = "https://api.edenai.run/v3/models"


def _edenai_per_million(per_token, label: str) -> float:
    # Eden AI's model-listing doc publishes the catalog's price fields as
    # per-token amounts ("input_cost_per_token": 1.5e-06,
    # edenai.co/docs/v3/llms/listing-models), so per-million rates scale
    # them by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _edenai_rates(model: dict, usd_per_eur: float) -> dict:
    # Discounted rows quote the billed price in `pricing` (`discount` is
    # the fraction off `list_pricing`), and the billed prices are what the
    # buyer pays. A missing cache_read_input_token_cost falls back to the
    # input rate; zero prices are kept.
    pricing = model.get("pricing") or {}
    cached = pricing.get("cache_read_input_token_cost")
    native = _rates(
        _edenai_per_million(pricing.get("input_cost_per_token"), "input"),
        _edenai_per_million(pricing.get("output_cost_per_token"), "output"),
        (
            _edenai_per_million(cached, "cache_read_input_token_cost")
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


def _edenai_capabilities(model: dict) -> dict:
    # The catalog nests its flags under capabilities
    # (capabilities.supports_reasoning, capabilities.
    # supports_function_calling) and modalities under
    # capabilities.input_modalities.
    caps = model.get("capabilities") or {}
    inputs = {
        str(value).lower() for value in caps.get("input_modalities") or []
    }
    return {
        "reasoning": bool(caps.get("supports_reasoning")),
        "tools": bool(caps.get("supports_function_calling")),
        "vision": bool({"image", "video", "pdf"} & inputs),
        "audio": "audio" in inputs,
    }


def _edenai_is_text_output(model: dict) -> bool:
    # The catalog nests modalities as
    # capabilities.output_modalities; rows publishing text output price
    # text tokens.
    outputs = (model.get("capabilities") or {}).get("output_modalities") or [
        "text"
    ]
    return "text" in {str(value).lower() for value in outputs}


def _edenai_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"edenai:{model['id']}",
        "router": "edenai",
        "routerName": "Eden AI",
        "modelId": model["id"],
        "name": model.get("model_name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description") or "",
        "releaseDate": None,
        "contextSize": model.get("context_length"),
        "capabilities": _edenai_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Eden AI's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_edenai_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Eden AI's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_edenai(exchange_rate)]


def fetch_edenai(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(EDENAI_URL), "Eden AI")
    offers = []
    seen_ids = set()
    for model in models:
        # The live catalog repeats a few ids with differing rows
        # (mistral/mistral-large-4, deepseek/deepseek-flash); the listing
        # key is the id, so repeats after the first stay out.
        if (
            not model.get("id")
            or model["id"] in seen_ids
            or not _edenai_is_text_output(model)
        ):
            continue
        try:
            default = _edenai_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices are not
            # per-million-token priced.
            continue
        seen_ids.add(model["id"])
        offers.append(_edenai_offer(model, default))
    if not offers:
        raise ValueError("Eden AI has no usable token-priced offers")
    return offers
