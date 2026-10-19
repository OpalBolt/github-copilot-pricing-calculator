"""OfoxAI adapter: USD catalog prices from OfoxAI's keyless model catalog,
converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

OFOX_URL = "https://api.ofox.ai/v2/models/catalog?include=provider_price&limit=500"


def _ofox_per_million(per_token, label: str) -> float:
    # OfoxAI's own pages render the catalog's per-token decimals as dollars
    # per 1M tokens (kimi-k3's pricing "0.000003"/"0.000015" renders as
    # "$3 / $15 /M"), so the per-token prices scale by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _ofox_rates(model: dict, usd_per_eur: float) -> dict:
    # Text models price input, output, and cached input per token in USD
    # ("Cached Tokens: Cache-hit input tokens (discounted rate)",
    # ofox.ai/docs/develop/observability/pricing; the balance API fixes the
    # account currency as "Currency unit, fixed to \"USD\"" with "All
    # amounts are in USD", ofox.ai/docs/api/openapi/balance); a missing
    # input_cache_read falls back to the input rate and zero prices are
    # kept. The other pricing fields (web_search, audio, per-image and
    # per-second rates, context_price_tiers) are not text-token rates and
    # are ignored.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_read")
    native = _rates(
        _ofox_per_million(pricing.get("input"), "input"),
        _ofox_per_million(pricing.get("output"), "output"),
        (
            _ofox_per_million(cached, "input_cache_read")
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


# The catalog's owned_by field also names the serving platform a model is
# reached through (Azure Foundry, AWS Bedrock, Alibaba DashScope,
# OpenRouter); the platform is not the creator.
_HOSTING_OWNERS = {"azure", "bedrock", "dashscope", "openrouter"}


def _ofox_owner(model: dict) -> str:
    # Serving-platform labels fall back to the id's vendor prefix
    # ("anthropic/claude-haiku-5.5" under bedrock, "qwen/qwen3.6-27b" under
    # dashscope); real creator orgs keep their owned_by spelling. A
    # prefix-less id carries no creator signal, so the row attributes to
    # the gateway itself instead of shipping an empty creator.
    owner = str(model.get("owned_by") or "").strip()
    if owner.lower() in _HOSTING_OWNERS:
        owner = model["id"].split("/", 1)[0] if "/" in model["id"] else ""
    return _creator(owner) or "OfoxAI"


def _ofox_capabilities(model: dict) -> dict:
    flags = model.get("capabilities") or {}
    return {
        "reasoning": bool(flags.get("reasoning")),
        "tools": bool(flags.get("function_calling")),
        "vision": bool(flags.get("vision")),
        "audio": bool(flags.get("audio_input")),
    }


def _ofox_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"ofox:{model['id']}",
        "router": "ofox",
        "routerName": "OfoxAI",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _ofox_owner(model),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _ofox_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in OfoxAI's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_ofox_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: OfoxAI's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_ofox(exchange_rate)]


def fetch_ofox(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(OFOX_URL), "OfoxAI")
    offers = []
    for model in models:
        # Only `mode: "chat"` rows are the text models OfoxAI bills per
        # token; image, video, audio, embedding, and decisions rows bill
        # per image, per second, or per request ("Because the units
        # differ, price sorting is performed within each provider's
        # group", ofox.ai).
        if not model.get("id") or model.get("mode") != "chat":
            continue
        try:
            default = _ofox_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Chat rows without per-token input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_ofox_offer(model, default))
    if not offers:
        raise ValueError("OfoxAI has no usable token-priced offers")
    return offers
