"""Empirio Labs adapter: USD catalog prices from Empirio Labs's keyless
model catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _catalog,
    _creator,
    _is_text_output,
    _rates,
    fetch_json,
    listing_from_offer,
)

EMPIRIOLABS_URL = "https://api.empiriolabs.ai/v1/models"


def _empiriolabs_per_million(per_token, label: str) -> float:
    # Empirio Labs prices per token: the catalog's pricing_rows render the
    # per-token decimal "0.0000014" as "$1.40 per 1M prompt tokens", so
    # per-million rates scale the decimals by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _empiriolabs_rates(pricing: dict, usd_per_eur: float) -> dict:
    # The catalog prices prompt, completion, and input_cache_read as
    # per-token decimals in USD; the `request` field prices per-call
    # features like web search and `image` prices images, so neither
    # feeds the token rates. A missing input_cache_read falls back to the
    # input rate; zero prices are kept.
    cached = pricing.get("input_cache_read")
    native = _rates(
        _empiriolabs_per_million(pricing.get("prompt"), "input"),
        _empiriolabs_per_million(pricing.get("completion"), "output"),
        (
            _empiriolabs_per_million(cached, "input_cache_read")
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


def _empiriolabs_base_pricing(model: dict) -> dict:
    # Tiered rows publish a list of pricing dicts; the first (threshold-
    # free) dict is the listing's base rate.
    pricing = model.get("pricing")
    if isinstance(pricing, list):
        return pricing[0] if pricing else {}
    return pricing or {}


def _empiriolabs_tiers(pricing, usd_per_eur: float) -> list[dict]:
    # The remaining dicts of a tiered row carry a min_context threshold;
    # they become the listing's pricingTiers in catalog order.
    if not isinstance(pricing, list):
        return []
    tiers = []
    for band in pricing:
        context_above = band.get("min_context")
        if context_above is None:
            continue
        rates = _empiriolabs_rates(band, usd_per_eur)
        tiers.append({"contextAbove": context_above, **rates})
    return tiers


def _empiriolabs_capabilities(model: dict) -> dict:
    # The catalog tags features per row ("reasoning", "function_calling",
    # "vision"), nests boolean flags under capabilities, and lists input
    # modalities at the top level.
    caps = model.get("capabilities") or {}
    inputs = {
        str(value).lower() for value in model.get("input_modalities") or []
    }
    features = {
        str(value).lower() for value in model.get("features") or []
    }
    return {
        "reasoning": bool(caps.get("reasoning") or "reasoning" in features),
        "tools": bool("function_calling" in features),
        "vision": bool(
            caps.get("images")
            or "vision" in features
            or {"image", "video", "pdf"} & inputs
        ),
        "audio": bool(caps.get("audio") or "audio" in inputs),
    }


def _empiriolabs_offer(model: dict, default: dict, tiers: list[dict]) -> dict:
    return {
        "key": f"empiriolabs:{model['id']}",
        "router": "empiriolabs",
        "routerName": "Empirio Labs",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        "owner": _creator(model.get("author")),
        "description": model.get("description") or "",
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _empiriolabs_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "pricingTiers": tiers,
        "priceNote": (
            "USD price published in Empirio Labs's model catalog and "
            "converted with the listed ECB rate."
        ),
    }


def fetch_empiriolabs_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Empirio Labs's catalog prices, re-noted
    as listing prices instead of routing-mode prices."""
    return [
        listing_from_offer(offer) for offer in fetch_empiriolabs(exchange_rate)
    ]


def fetch_empiriolabs(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(EMPIRIOLABS_URL), "Empirio Labs")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _empiriolabs_rates(
                _empiriolabs_base_pricing(model), exchange_rate["usdPerEur"]
            )
            tiers = _empiriolabs_tiers(
                model.get("pricing"), exchange_rate["usdPerEur"]
            )
        except ValueError:
            # Rows without per-token prompt and completion prices are not
            # per-million-token priced.
            continue
        offers.append(_empiriolabs_offer(model, default, tiers))
    if not offers:
        raise ValueError("Empirio Labs has no usable token-priced offers")
    return offers
