"""OpenCode Zen adapter: USD router prices from Zen's catalog with models.dev
metadata."""

from sources.helpers import (
    _capabilities,
    _catalog,
    _converted_usd_rates,
    _is_text_output,
    fetch_json,
)

OPENCODE_ZEN_URL = "https://opencode.ai/zen/v1/models"
MODELS_DEV_URL = "https://models.dev/api.json"


def _opencode_owner(model: dict) -> str:
    model_id = model["id"].lower()
    owners = {
        "claude": "Anthropic",
        "deepseek": "DeepSeek",
        "gemini": "Google",
        "glm": "Z.ai",
        "gpt": "OpenAI",
        "grok": "xAI",
        "kimi": "Moonshot AI",
        "minimax": "MiniMax AI",
        "mimo": "Xiaomi",
        "muse": "Meta",
        "nemotron": "NVIDIA",
        "qwen": "Alibaba",
    }
    return next(
        (owner for prefix, owner in owners.items() if model_id.startswith(prefix)),
        "OpenCode",
    )


def _opencode_tiers(cost: dict, usd_per_eur: float) -> list[dict]:
    tiers = []
    for tier in cost.get("tiers", []):
        threshold = tier.get("tier", {})
        if threshold.get("type") != "context" or threshold.get("size") is None:
            continue
        rates = _converted_usd_rates(tier, usd_per_eur)
        tiers.append({"contextAbove": threshold["size"], **rates})
    return sorted(tiers, key=lambda tier: tier["contextAbove"])


def fetch_opencode(exchange_rate: dict) -> list[dict]:
    available = {
        model["id"]
        for model in _catalog(fetch_json(OPENCODE_ZEN_URL), "OpenCode Zen")
        if model.get("id")
    }
    provider = fetch_json(MODELS_DEV_URL).get("opencode", {})
    models = provider.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("OpenCode Zen metadata catalog has no models")

    offers = []
    for model_id in sorted(available):
        model = models.get(model_id)
        if not model or not _is_text_output(model):
            continue
        cost = model.get("cost", {})
        try:
            default = _converted_usd_rates(cost, exchange_rate["usdPerEur"])
        except ValueError:
            continue
        tiers = _opencode_tiers(cost, exchange_rate["usdPerEur"])
        offers.append(
            {
                "key": f"opencode:{model_id}",
                "router": "opencode",
                "routerName": "OpenCode Zen",
                "modelId": model_id,
                "name": model.get("name") or model_id,
                "owner": _opencode_owner(model),
                "description": model.get("description", ""),
                "releaseDate": model.get("release_date"),
                "contextSize": model.get("limit", {}).get("context"),
                "capabilities": _capabilities(model),
                "providers": [],
                "euProviders": [],
                "default": default,
                "pricingTiers": tiers,
                "eu": None,
                "quantization": None,
                "priceNote": (
                    "USD Router Price published in OpenCode's model catalog and "
                    "converted with the listed ECB rate."
                ),
            }
        )
    if not offers:
        raise ValueError("OpenCode Zen has no usable text-output offers")
    return offers
