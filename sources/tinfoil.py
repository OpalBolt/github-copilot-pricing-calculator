"""Tinfoil adapter: USD catalog prices from Tinfoil's keyless model
catalog, converted with the listed ECB rate."""

from sources.helpers import (
    _catalog,
    _creator,
    _rates,
    fetch_json,
    listing_from_offer,
)

TINFOIL_URL = "https://inference.tinfoil.sh/v1/models"


def _tinfoil_rates(model: dict, usd_per_eur: float) -> dict:
    # The catalog's price fields are named *TokenPricePer1M — already
    # dollars per 1M tokens — so they pass through unmultiplied; a missing
    # cachedInputTokenPricePer1M falls back to the input rate and zero
    # prices are kept.
    pricing = model.get("pricing") or {}
    native = _rates(
        pricing.get("inputTokenPricePer1M"),
        pricing.get("outputTokenPricePer1M"),
        pricing.get("cachedInputTokenPricePer1M"),
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


def _tinfoil_is_chat_priced(model: dict) -> bool:
    # Two catalog shapes are not per-token chat usage: rows with a
    # requestPrice (privacy filter, document processing, web search,
    # transcription, TTS, realtime bill per request — their zero token
    # prices are an absence, not a price) and rows without a chat
    # completions or responses endpoint (the embedding row bills input
    # tokens only and produces no completion tokens).
    pricing = model.get("pricing") or {}
    if pricing.get("requestPrice"):
        return False
    endpoints = set(model.get("endpoints") or [])
    return bool(endpoints & {"/v1/chat/completions", "/v1/responses"})


def _tinfoil_owner(model: dict) -> str:
    # The catalog names every row owned_by "tinfoil" — the serving
    # platform, not an upstream creator — and the ids carry no vendor
    # prefix, so rows attribute to Tinfoil itself (the registry's display
    # name) instead of shipping the platform string as a creator.
    owner = _creator(model.get("owned_by"))
    return "Tinfoil" if owner.lower() in {"", "tinfoil"} else owner


def _tinfoil_capabilities(model: dict) -> dict:
    # The shared _capabilities reads supported_features and input
    # modality lists — shapes this catalog doesn't publish — so the
    # declared flags drive the derivation: reasoning and tool_calling
    # name their capabilities directly, multimodal marks image input,
    # and the audio model type marks audio input.
    reasoning = model.get("reasoning")
    return {
        "reasoning": bool(
            reasoning is True
            or (
                isinstance(reasoning, dict)
                and (
                    reasoning.get("mandatory")
                    or reasoning.get("supported_efforts")
                )
            )
        ),
        "tools": bool(model.get("tool_calling")),
        "vision": bool(model.get("multimodal")),
        "audio": model.get("type") == "audio",
    }


def _tinfoil_offer(model: dict, default: dict) -> dict:
    return {
        "key": f"tinfoil:{model['id']}",
        "router": "tinfoil",
        "routerName": "Tinfoil",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _tinfoil_owner(model),
        "description": model.get("description", ""),
        "releaseDate": None,
        "contextSize": model.get("context_window"),
        "capabilities": _tinfoil_capabilities(model),
        "providers": [],
        "euProviders": [],
        "default": default,
        "eu": None,
        "quantization": None,
        "priceNote": (
            "USD price published in Tinfoil's model catalog and converted "
            "with the listed ECB rate."
        ),
    }


def fetch_tinfoil_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Tinfoil's catalog prices, re-noted as
    listing prices instead of routing-mode prices."""
    return [listing_from_offer(offer) for offer in fetch_tinfoil(exchange_rate)]


def fetch_tinfoil(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(TINFOIL_URL), "Tinfoil")
    offers = []
    for model in models:
        if not model.get("id") or not _tinfoil_is_chat_priced(model):
            continue
        try:
            default = _tinfoil_rates(model, exchange_rate["usdPerEur"])
        except ValueError:
            # Rows without published input and output prices are not
            # per-million-token priced.
            continue
        offers.append(_tinfoil_offer(model, default))
    if not offers:
        raise ValueError("Tinfoil has no usable token-priced offers")
    return offers
