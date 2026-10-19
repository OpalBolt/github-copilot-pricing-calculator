"""NEAR AI adapter: USD catalog prices from NEAR AI Cloud's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _is_text_output,
    _rates,
    fetch_json,
    listing_from_offer,
)

NEARAI_URL = "https://cloud-api.near.ai/v1/models"

# The catalog's owned_by field also carries NEAR AI's own hosting label and
# its "attested 3p" privacy tier; both name the serving fleet, not the
# creator.
_HOSTING_OWNERS = {"nearai", "attested 3p"}


def _nearai_per_million(per_token, label: str) -> float:
    # NEAR AI's pricing API stores every price per token with "a fixed
    # scale of 9 (nano-dollars = 1 billionth of a dollar)"
    # (docs.near.ai/api-reference/models/list-models-with-pricing), so the
    # catalog's prompt, completion, and input_cache_read decimal strings
    # scale by 1,000,000 into dollars per 1M tokens (claude-fable-5's
    # inputCostPerToken 10000 at scale 9 is the catalog's prompt
    # "0.00001"; the numeric input field duplicates it as 10.0).
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _nearai_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog prices input, output, and cached input per token in USD
    # under prompt, completion, and input_cache_read (the prompt-caching
    # guide names pricing.input_cache_read the discounted cache-read
    # rate); the numeric input and output fields equal prompt and
    # completion times 1,000,000 on every catalog row, and a missing
    # input_cache_read falls back to the input rate. Zero prices stay. A
    # textPricing.currency marker naming anything but USD means the row is
    # not priced in the nano-dollar USD decimals this adapter scales;
    # raising ValueError skips the row instead of shipping a distorted
    # price.
    pricing = model.get("pricing") or {}
    currency = (model.get("textPricing") or {}).get("currency")
    if currency is not None and currency != "USD":
        raise ValueError(f"textPricing currency {currency} is not USD")
    cached = pricing.get("input_cache_read")
    native = _rates(
        _nearai_per_million(pricing.get("prompt"), "input"),
        _nearai_per_million(pricing.get("completion"), "output"),
        (
            _nearai_per_million(cached, "input_cache_read")
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


def _nearai_owner(model: dict) -> str:
    # Hosting labels fall back to the id's vendor prefix
    # ("Qwen/Qwen3.6-35B-A3B-FP8", "deepseek/deepseek-v3.2"); real creator
    # orgs keep their owned_by spelling. A prefix-less id carries no
    # creator signal, so the row attributes to the gateway itself (the
    # same fallback opencode.py uses) instead of shipping an empty
    # creator.
    owner = str(model.get("owned_by") or "").strip()
    if owner.lower() in _HOSTING_OWNERS:
        owner = model["id"].split("/", 1)[0] if "/" in model["id"] else ""
    return _creator(owner) or "NEAR AI"


def _nearai_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"nearai:{model['id']}",
        "router": "nearai",
        "routerName": "NEAR AI",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _nearai_owner(model),
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
            "USD price published in NEAR AI's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_nearai_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: NEAR AI's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_nearai(exchange_rate)]


def fetch_nearai(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(NEARAI_URL), "NEAR AI")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _nearai_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices (per-request
            # or per-image billing) and rows whose textPricing.currency
            # marker names another currency are not per-million-token USD
            # priced and skip the row.
            continue
        offers.append(_nearai_offer(model, default))
    if not offers:
        raise ValueError("NEAR AI has no usable token-priced offers")
    return offers
