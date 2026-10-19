"""AI/ML API adapter: USD catalog prices from AI/ML API's keyless model
catalog, converted with the listed ECB rate."""

from decimal import Decimal, InvalidOperation

from sources.helpers import (
    _capabilities,
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

AIMLAPI_URL = "https://api.aimlapi.com/v1/models?include=pricing,modalities"

# The catalog lists one row per model per endpoint under `type`. The
# chat-completions rows carry the complete per-token chat prices; the same
# model's batches, messages, and responses rows subset them, and its
# text-to-speech, image, video, OCR, and speech-to-text endpoints price
# other services entirely.
CHAT_COMPLETIONS = "openai/chat-completions"


def _aimlapi_per_million(unit: dict, label: str) -> float:
    # AI/ML API's Complete Model List doc: "Always read `per` together with
    # `price`. `price` is the charge for `per` units" — `per` is 1000000
    # for most token rates and 1000 for some, so the USD rate scales by
    # 1,000,000/per.
    try:
        result = (
            Decimal(str(unit["price"]))
            * Decimal(1_000_000)
            / Decimal(str(unit["per"]))
        )
    except (KeyError, InvalidOperation, TypeError, ZeroDivisionError) as error:
        raise ValueError(f"{label} is not a per-token price") from error
    if result < 0:
        raise ValueError(f"{label} is negative")
    return float(result)


def _aimlapi_unit(units: list, origin: str, phase: str):
    """The catalog's text-token charge for one token stream, or None when
    the row publishes no such unit."""
    for unit in units:
        if (
            unit.get("name") == "token"
            and unit.get("content") == "text"
            and unit.get("origin") == origin
            and unit.get("phase") == phase
        ):
            return unit
    return None


def _aimlapi_rates(model: dict, usd_per_eur: float) -> dict:
    # The pricing units price text tokens by origin: "provided" is the
    # input stream, "cached" the cached input, and "generated" inference
    # the output; the generated "reasoning" phase repeats the output
    # charge. A missing cached unit falls back to the input rate and zero
    # prices are kept.
    units = (model.get("pricing") or {}).get("units") or []
    cached_unit = _aimlapi_unit(units, "cached", "inference")
    native = _rates(
        _aimlapi_per_million(
            _aimlapi_unit(units, "provided", "inference"), "input"
        ),
        _aimlapi_per_million(
            _aimlapi_unit(units, "generated", "inference"), "output"
        ),
        _aimlapi_per_million(cached_unit, "cached") if cached_unit else None,
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


def _aimlapi_offer(model: dict, default: dict) -> dict:
    info = model.get("info") or {}
    return {
        "key": f"aimlapi:{model['id']}",
        "router": "aimlapi",
        "routerName": "AI/ML API",
        "modelId": model["id"],
        "name": info.get("name") or model["id"],
        "owner": _creator(info.get("developer")),
        "description": info.get("description", ""),
        "releaseDate": None,
        "contextSize": info.get("contextLength"),
        "capabilities": _capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in AI/ML API's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_aimlapi_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: AI/ML API's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_aimlapi(exchange_rate)]


def fetch_aimlapi(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(AIMLAPI_URL), "AI/ML API")
    offers = []
    for model in models:
        if not model.get("id") or model.get("type") != CHAT_COMPLETIONS:
            continue
        try:
            default = _aimlapi_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without text-token input and output prices (the dynamic
            # routers, and the per-second and per-page endpoints) are not
            # per-million-token priced.
            continue
        offers.append(_aimlapi_offer(model, default))
    if not offers:
        raise ValueError("AI/ML API has no usable token-priced offers")
    return offers
