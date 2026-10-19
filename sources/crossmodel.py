"""Crossmodel adapter: USD catalog prices from CrossModel's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

CROSSMODEL_URL = "https://www.crossmodel.ai/api/models"


def _crossmodel_per_million(micro, label: str) -> float:
    # CrossModel bills amounts in "micro units of currency (1 USD =
    # 1,000,000 micro); divide by 1,000,000 for the decimal amount"
    # (crossmodel.ai/docs/api-reference/usage), so the catalog's
    # input_micro_per_1m fields divide by 1,000,000 into dollars per 1M
    # tokens.
    try:
        result = Decimal(str(micro)) / Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _crossmodel_tier_rates(tier: dict, usd_per_eur: float) -> dict:
    # One pricing tier prices input (input_micro_per_1m), output
    # (output_micro_per_1m), and cache reads (cache_read_micro_per_1m) in
    # micro-dollars per 1M tokens; a missing cache_read_micro_per_1m falls
    # back to the input rate and zero prices are kept. The decision models'
    # zero output and cache prices are published prices: they are "billed
    # on input tokens only" (crossmodel.ai/docs/billing).
    native = _rates(
        _crossmodel_per_million(tier.get("input_micro_per_1m"), "input rate"),
        _crossmodel_per_million(tier.get("output_micro_per_1m"), "output rate"),
        (
            _crossmodel_per_million(
                tier.get("cache_read_micro_per_1m"), "cache read rate"
            )
            if tier.get("cache_read_micro_per_1m") is not None
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


def _crossmodel_pricing(model: dict) -> list[dict]:
    # pricing.tiers carries the billed prices — promoted rows pair them
    # with the pre-promotion list_tiers — ordered from the threshold-0
    # base tier through the long-context thresholds.
    tiers = (model.get("pricing") or {}).get("tiers") or []
    if not tiers:
        raise ValueError("pricing has no tiers")
    return tiers


def _crossmodel_rates(model: dict, usd_per_eur: float) -> dict:
    return _crossmodel_tier_rates(_crossmodel_pricing(model)[0], usd_per_eur)


def _crossmodel_tiers(model: dict, usd_per_eur: float) -> list[dict]:
    # The threshold tiers after the base row are the long-context tiers;
    # each lists at its own contextAbove like the other sellers' tiers.
    priced = []
    for tier in _crossmodel_pricing(model)[1:]:
        if tier.get("threshold") is None:
            continue
        priced.append(
            {
                "contextAbove": tier["threshold"],
                **_crossmodel_tier_rates(tier, usd_per_eur),
            }
        )
    return sorted(priced, key=lambda tier: tier["contextAbove"])


def _crossmodel_capabilities(model: dict) -> dict:
    # The catalog nests its capability flags under capabilities
    # (capabilities.reasoning.supported, capabilities.tool_use.supported),
    # and modalities.input names the accepted inputs.
    caps = model.get("capabilities") or {}
    inputs = {
        str(value).lower()
        for value in (model.get("modalities") or {}).get("input") or []
    }
    reasoning = caps.get("reasoning") or {}
    tool_use = caps.get("tool_use") or {}
    return {
        "reasoning": reasoning.get("supported") is True,
        "tools": tool_use.get("supported") is True,
        "vision": bool({"image", "vision", "video", "pdf"} & inputs),
        "audio": "audio" in inputs,
    }


def _crossmodel_offer(model: dict, default: dict, tiers: list[dict]) -> dict:
    return {
        "key": f"crossmodel:{model['id']}",
        "router": "crossmodel",
        "routerName": "Crossmodel",
        "modelId": model["id"],
        "name": model.get("display_name") or model["id"],
        # The id's vendor prefix ("anthropic/claude-opus-5") is the
        # model's author; the catalog's provider field names the upstream
        # route (claude-opus-5 routes via OpenRouter), not the creator.
        "owner": _creator(model["id"].split("/", 1)[0]),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window_tokens"),
        "capabilities": _crossmodel_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "pricingTiers": tiers,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Crossmodel's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_crossmodel_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Crossmodel's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_crossmodel(exchange_rate)]


def fetch_crossmodel(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(CROSSMODEL_URL), "Crossmodel")
    offers = []
    for model in models:
        if not model.get("id"):
            continue
        try:
            default = _crossmodel_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without input and output prices in their base tier are
            # not token-priced and skip the row.
            continue
        offers.append(
            _crossmodel_offer(
                model,
                default,
                _crossmodel_tiers(model, exchange_rate["usdPerEur"]),
            )
        )
    if not offers:
        raise ValueError("Crossmodel has no usable token-priced offers")
    return offers
