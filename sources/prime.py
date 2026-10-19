"""Prime adapter: USD catalog prices from Prime Intellect's keyless Prime
Inference model catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

PRIME_URL = "https://api.pinference.ai/api/v1/models"


def _prime_rates(pricing: dict, usd_per_eur: float) -> dict:
    # Prime's catalog prices are already dollars per 1M tokens — the price
    # fields are named *_usd_per_mtok — so they pass through unmultiplied;
    # a missing cache_read_usd_per_mtok falls back to the input rate and
    # zero prices are kept.
    native = _rates(
        pricing.get("input_usd_per_mtok"),
        pricing.get("output_usd_per_mtok"),
        pricing.get("cache_read_usd_per_mtok"),
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


def _prime_owner(model: dict) -> str:
    # The catalog leaves owned_by empty; the id prefix names the owner. A
    # prefix-less id carries no creator signal, so the row attributes to
    # Prime Intellect's own name (the registry's display name) instead of
    # shipping an empty creator.
    owner = model["id"].split("/", 1)[0] if "/" in model["id"] else ""
    return _creator(owner) or "Prime Intellect"


def _prime_capabilities(model: dict) -> dict:
    # The catalog nests modalities under specs.modalities — a shape the
    # shared _capabilities doesn't read — so the declared input modalities
    # drive vision and audio locally; reasoning and tools read the
    # reasoning effort dict and supported_parameters.
    inputs = {
        str(value).lower()
        for value in ((model.get("specs") or {}).get("modalities") or {}).get(
            "input"
        )
        or []
    }
    features = {
        str(value).lower()
        for value in model.get("supported_features")
        or model.get("supported_parameters")
        or []
    }
    reasoning = model.get("reasoning")
    return {
        "reasoning": bool(
            {"reasoning", "include_reasoning"} & features
            or reasoning is True
            or (
                isinstance(reasoning, dict)
                and (
                    reasoning.get("mandatory")
                    or reasoning.get("supported_efforts")
                )
            )
        ),
        "tools": bool({"tools", "tool_choice"} & features or model.get("tool_call")),
        "vision": bool({"image", "vision", "video", "pdf"} & inputs),
        "audio": "audio" in inputs,
    }


def _prime_is_text_output(model: dict) -> bool:
    # The catalog nests modalities under specs.modalities.output — a shape
    # the shared _is_text_output never reads, so its ["text"] default kept
    # every Prime row (the decisions-only clef included) by accident.
    # Declared outputs drive the filter: a row without text output still
    # lists when the catalog publishes its token prices (zero prices are
    # prices — clef's per-token rate prices its decisions), while
    # image-output rows bill images, not tokens, and stay out.
    outputs = {
        str(value).lower()
        for value in ((model.get("specs") or {}).get("modalities") or {}).get(
            "output"
        )
        or ["text"]
    }
    if "text" in outputs:
        return True
    pricing = model.get("pricing") or {}
    try:
        _rates(
            pricing.get("input_usd_per_mtok"),
            pricing.get("output_usd_per_mtok"),
            native_currency="USD",
        )
    except ValueError:
        return False
    return True


def _prime_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"prime:{model['id']}",
        "router": "prime",
        "routerName": "Prime",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _prime_owner(model),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _prime_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Prime's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_prime_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Prime's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_prime(exchange_rate)]


def fetch_prime(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(PRIME_URL), "Prime")
    offers = []
    for model in models:
        if not model.get("id") or not _prime_is_text_output(model):
            continue
        try:
            default = _prime_rates(
                model.get("pricing") or {}, exchange_rate["usdPerEur"]
            )
        except ValueError:
            # Rows without published input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_prime_offer(model, default))
    if not offers:
        raise ValueError("Prime has no usable token-priced offers")
    return offers
