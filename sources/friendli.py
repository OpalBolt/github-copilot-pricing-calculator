"""FriendliAI adapter: USD catalog prices from FriendliAI's keyless serverless
model catalog, converted with the listed ECB rate."""

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

FRIENDLI_URL = "https://api.friendli.ai/serverless/v1/models"


def _friendli_per_million(per_token, label: str) -> float:
    # FriendliAI's pricing page renders the catalog's price fields as
    # dollars per 1M tokens (the embedded GLM-5.3 rate card: unit "1M
    # tokens", inputPrice 1.4 for the catalog's "0.0000014"), so the
    # per-token prices scale by 1,000,000.
    try:
        result = Decimal(str(per_token)) * Decimal(1_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} is not numeric") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _friendli_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog prices input, output, and input_cache_read per token in
    # US dollars; a missing input_cache_read falls back to the input rate
    # and zero prices are kept.
    pricing = model.get("pricing") or {}
    cached = pricing.get("input_cache_read")
    native = _rates(
        _friendli_per_million(pricing.get("input"), "input"),
        _friendli_per_million(pricing.get("output"), "output"),
        (
            _friendli_per_million(cached, "input_cache_read")
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


def _friendli_capabilities(model: dict) -> dict:
    # The shared helper reads the top-level reasoning flag and input
    # modalities; Friendli nests tool support under `functionality`.
    capabilities = _capabilities(model)
    capabilities["tools"] = bool(
        capabilities["tools"] or (model.get("functionality") or {}).get("tool_call")
    )
    return capabilities


def _friendli_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"friendli:{model['id']}",
        "router": "friendli",
        "routerName": "FriendliAI",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(
            model["id"].split("/", 1)[0] if "/" in model["id"] else ""
        ),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_length"),
        "capabilities": _friendli_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in FriendliAI's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_friendli_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: FriendliAI's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_friendli(exchange_rate)]


def fetch_friendli(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(FRIENDLI_URL), "FriendliAI")
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _friendli_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without per-token input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_friendli_offer(model, default))
    if not offers:
        raise ValueError("FriendliAI has no usable token-priced offers")
    return offers
