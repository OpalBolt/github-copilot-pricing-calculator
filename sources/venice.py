"""Venice adapter: USD catalog prices from Venice's keyless model
catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

VENICE_URL = "https://api.venice.ai/api/v1/models?type=text"


def _venice_usd_price(price, label: str) -> float:
    # The catalog quotes every rate twice — usd and diem — and the
    # calculator bills the USD field ("All prices in USD",
    # docs.venice.ai/overview/pricing).
    if not isinstance(price, dict) or price.get("usd") is None:
        raise ValueError(f"{label} has no usd price")
    return price["usd"]


def _venice_rates(pricing: dict, usd_per_eur: float) -> dict:
    # The catalog's usd fields are already dollars per 1M tokens ("USD
    # cost per million input tokens", docs.venice.ai/api-reference/
    # endpoint/models/list), so they pass through unmultiplied; a missing
    # cache_input falls back to the input rate and zero prices are kept.
    native = _rates(
        _venice_usd_price(pricing.get("input"), "input"),
        _venice_usd_price(pricing.get("output"), "output"),
        (
            _venice_usd_price(pricing.get("cache_input"), "cache_input")
            if pricing.get("cache_input")
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


def _venice_pricing_tiers(pricing: dict, usd_per_eur: float) -> list[dict]:
    # pricing.extended is the long-context tier: the same per-million usd
    # fields with the input token count above which it applies
    # (context_token_threshold).
    extended = pricing.get("extended")
    threshold = (extended or {}).get("context_token_threshold")
    if not extended or not threshold:
        return []
    return [
        {"contextAbove": threshold, **_venice_rates(extended, usd_per_eur)}
    ]


def _venice_capabilities(model: dict) -> dict:
    # The shared _capabilities reads supported_features and input modality
    # lists — shapes this catalog doesn't publish — so the declared flags
    # drive the derivation: supportsReasoning, supportsFunctionCalling,
    # supportsVision, and supportsAudioInput name their capabilities
    # directly.
    flags = (model.get("model_spec") or {}).get("capabilities") or {}
    return {
        "reasoning": bool(flags.get("supportsReasoning")),
        "tools": bool(flags.get("supportsFunctionCalling")),
        "vision": bool(flags.get("supportsVision")),
        "audio": bool(flags.get("supportsAudioInput")),
    }


def _venice_owner(model: dict) -> str:
    # The catalog names every row owned_by "venice.ai" — the serving
    # platform, not an upstream creator — and Venice anonymizes third-party
    # models' identifying metadata, so rows attribute to Venice itself (the
    # registry's display name) instead of shipping the platform string as a
    # creator.
    owner = _creator(model.get("owned_by"))
    return "Venice" if owner.lower() in {"", "venice.ai", "veniceai"} else owner


def _venice_offer(model: dict, default: dict, pricing_tiers: list[dict]) -> dict:
    spec = model.get("model_spec") or {}
    return {
        "key": f"venice:{model['id']}",
        "router": "venice",
        "routerName": "Venice",
        "modelId": model["id"],
        "name": spec.get("name") or model["id"],
        "owner": _venice_owner(model),
        "description": spec.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_length"),
        "capabilities": _venice_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "pricingTiers": pricing_tiers,
        "priceNote": (
            "USD price published in Venice's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_venice_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Venice's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_venice(exchange_rate)]


def fetch_venice(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(VENICE_URL), "Venice")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        pricing = (model.get("model_spec") or {}).get("pricing") or {}
        try:
            default = _venice_rates(pricing, exchange_rate["usdPerEur"])
            tiers = _venice_pricing_tiers(pricing, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without published input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_venice_offer(model, default, tiers))
    if not offers:
        raise ValueError("Venice has no usable token-priced offers")
    return offers
