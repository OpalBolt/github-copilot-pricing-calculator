#!/usr/bin/env python3
"""Fetch and normalize bulk model catalogs for the router calculator."""

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fetch_providers import (
    DEEPSEEK_URL,
    ZAI_PAYGO_URL,
    fetch_text,
    parse_markdown_tables,
    parse_price,
    scrape_deepseek,
    scrape_zai_paygo,
)

ROOT = Path(__file__).parent
OUTPUT_PATH = ROOT / "router-pricing.json"
MAX_STALE_AGE = timedelta(days=7)

CORTECS_URL = "https://api.cortecs.ai/v1/models?extended=true&currency=EUR"
CORTECS_EU_URL = CORTECS_URL + "&eu_native=true"
EUROUTER_URL = "https://api.eurouter.ai/api/v1/models"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_EU_URL = "https://eu.openrouter.ai/api/v1/models"
OPENCODE_ZEN_URL = "https://opencode.ai/zen/v1/models"
MODELS_DEV_URL = "https://models.dev/api.json"
CLAUDE_MODELS_URL = "https://platform.claude.com/docs/en/api/http/beta/models/list.md"
CLAUDE_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
OPENAI_MODELS_URL = (
    "https://developers.openai.com/api/reference/resources/models/methods/list"
)
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
ECB_SERIES = "EXR.D.USD.EUR.SP00.A"
ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    "?format=csvdata&startPeriod={start}"
)

OWNER_ALIASES = {
    "alibaba": "Alibaba",
    "alibabacloud": "Alibaba",
    "alibabaqwen": "Alibaba",
    "amazon": "Amazon",
    "amazonwebservices": "Amazon",
    "anthropic": "Anthropic",
    "bytedance": "ByteDance",
    "bytedanceseed": "ByteDance",
    "deepseek": "DeepSeek",
    "google": "Google",
    "meta": "Meta",
    "metaai": "Meta",
    "metallama": "Meta",
    "minimax": "MiniMax AI",
    "minimaxai": "MiniMax AI",
    "mistralai": "Mistral AI",
    "moonshotai": "Moonshot AI",
    "nousresearch": "Nous Research",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "qwen": "Alibaba",
    "xiaomi": "Xiaomi",
    "xai": "xAI",
    "zai": "Z.ai",
    "zhipu": "Z.ai",
    "zhipuai": "Z.ai",
}

PROVIDER_ALIASES = {
    "inceptron": "Inceptron",
    "infercom": "Infercom",
    "nebius": "Nebius",
    "scaleway": "Scaleway",
    "tensorix": "Tensorix",
}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/csv",
            "User-Agent": "github-copilot-pricing-calculator/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_json(url: str) -> dict:
    return json.loads(fetch_bytes(url).decode("utf-8"))


def _number(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not numeric") from error
    if number < 0:
        raise ValueError(f"{label} is negative")
    return number


def _catalog(payload: dict, router: str) -> list[dict]:
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list) or not models:
        raise ValueError(f"{router} catalog has no data list")
    return models


def _rates(input_rate, output_rate, cached_rate=None, *, native_currency="EUR") -> dict:
    input_value = _number(input_rate, "input rate")
    output_value = _number(output_rate, "output rate")
    fallback = cached_rate is None
    cached_value = input_value if fallback else _number(cached_rate, "cached input rate")
    return {
        "input": input_value,
        "cached": cached_value,
        "output": output_value,
        "cachedFallback": fallback,
        "nativeCurrency": native_currency,
    }


def _capabilities(model: dict) -> dict[str, bool]:
    inputs = {
        str(value).lower()
        for value in (
            model.get("input_modalities")
            or model.get("architecture", {}).get("input_modalities")
            or model.get("modalities", {}).get("input")
            or []
        )
    }
    features = {
        str(value).lower()
        for value in (
            model.get("supported_features")
            or model.get("supported_parameters")
            or []
        )
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


def _is_text_output(model: dict) -> bool:
    outputs = (
        model.get("output_modalities")
        or model.get("architecture", {}).get("output_modalities")
        or ["text"]
    )
    return "text" in {str(value).lower() for value in outputs}


def _organization_name(value, aliases: dict[str, str]) -> str:
    name = str(value or "").strip().lstrip("~").strip()
    key = re.sub(r"[^a-z0-9]+", "", name.lower())
    return aliases.get(key, name)


def _creator(value) -> str:
    return _organization_name(value, OWNER_ALIASES)


def _provider(value) -> str:
    return _organization_name(value, PROVIDER_ALIASES)


def _heavy_quantization(model: dict, rates: dict) -> str | None:
    for details in model.get("providers_details", {}).values():
        pricing = details.get("pricing", {})
        if (
            pricing.get("input_token") == rates["input"]
            and pricing.get("output_token") == rates["output"]
            and pricing.get("cache_read_cost") == (
                None if rates["cachedFallback"] else rates["cached"]
            )
            and str(details.get("quantization", "")).lower() in {"fp4", "int4"}
        ):
            return str(details["quantization"]).lower()
    return None


def _cortecs_offer(model: dict, eu_model: dict | None) -> dict:
    pricing = model.get("pricing", {})
    default = _rates(
        pricing.get("input_token"),
        pricing.get("output_token"),
        pricing.get("cache_read_cost"),
    )
    eu = None
    eu_providers = []
    if eu_model:
        eu_pricing = eu_model.get("pricing", {})
        eu = _rates(
            eu_pricing.get("input_token"),
            eu_pricing.get("output_token"),
            eu_pricing.get("cache_read_cost"),
        )
        eu_providers = [_provider(name) for name in eu_model.get("providers", [])]
    return {
        "key": f"cortecs:{model['id']}",
        "router": "cortecs",
        "routerName": "Cortecs",
        "modelId": model["id"],
        "name": model.get("name") or model["id"],
        "owner": _creator(model.get("owned_by")),
        "description": model.get("description", ""),
        "releaseDate": model.get("release_date"),
        "contextSize": model.get("context_size"),
        "capabilities": _capabilities(model),
        "providers": [_provider(name) for name in model.get("providers", [])],
        "euProviders": eu_providers,
        "default": default,
        "eu": eu,
        "quantization": _heavy_quantization(model, default),
        "priceNote": "Model-level minimum price published by Cortecs.",
    }


def fetch_cortecs() -> list[dict]:
    models = _catalog(fetch_json(CORTECS_URL), "Cortecs")
    eu_models = {
        model["id"]: model
        for model in _catalog(fetch_json(CORTECS_EU_URL), "Cortecs EU")
        if model.get("id")
    }
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        offers.append(_cortecs_offer(model, eu_models.get(model["id"])))
    if not offers:
        raise ValueError("Cortecs has no usable text-output offers")
    return offers


def _pricing_value(pricing: dict, *keys: str):
    for key in keys:
        if pricing.get(key) is not None:
            return pricing[key]
    return None


def _per_million_rates(pricing: dict, *, native_currency: str) -> dict:
    input_rate = _pricing_value(pricing, "input_token", "input", "prompt")
    output_rate = _pricing_value(pricing, "output_token", "output", "completion")
    cached_rate = _pricing_value(
        pricing,
        "cache_read_cost",
        "cached_input",
        "input_cache_read",
        "cache_read",
    )
    if input_rate is None or output_rate is None:
        raise ValueError("pricing is missing input or output")

    unit = pricing.get("unit") or pricing.get("units")
    if unit in {"token", "per_token"} or any(
        key in pricing for key in ("prompt", "completion", "input_cache_read")
    ):
        def per_million(value, label):
            try:
                result = Decimal(str(value)) * Decimal(1_000_000)
            except InvalidOperation as error:
                raise ValueError(f"{label} is not numeric") from error
            if result < 0:
                raise ValueError(f"{label} is negative")
            return float(result)

        input_rate = per_million(input_rate, "input rate")
        output_rate = per_million(output_rate, "output rate")
        if cached_rate is not None:
            cached_rate = per_million(cached_rate, "cached input rate")
    return _rates(
        input_rate,
        output_rate,
        cached_rate,
        native_currency=native_currency,
    )


def _usd_rates(model: dict, usd_per_eur: float) -> dict:
    native = _per_million_rates(model.get("pricing", {}), native_currency="USD")
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
            "input": native["input"],
            "cached": native["cached"],
            "output": native["output"],
        },
    }


def fetch_eurouter(exchange_rate: dict | None = None) -> list[dict]:
    models = _catalog(fetch_json(EUROUTER_URL), "EUrouter")
    offers = []
    for model in models:
        endpoints = set(model.get("supported_api_endpoints") or [])
        pricing = model.get("pricing", {})
        currency = pricing.get("currency")
        if (
            not model.get("id")
            or not _is_text_output(model)
            or "chat.completions" not in endpoints
            or currency not in {"EUR", "USD"}
            or (currency == "USD" and not exchange_rate)
        ):
            continue
        try:
            rates = (
                _per_million_rates(pricing, native_currency="EUR")
                if currency == "EUR"
                else _usd_rates(model, exchange_rate["usdPerEur"])
            )
        except ValueError:
            continue
        providers = model.get("providers") or []
        if providers and isinstance(providers[0], dict):
            providers = [
                provider.get("name") or provider.get("id")
                for provider in providers
                if provider.get("name") or provider.get("id")
            ]
        providers = [_provider(name) for name in providers]
        offer = {
            "key": f"eurouter:{model['id']}",
            "router": "eurouter",
            "routerName": "EUrouter",
            "modelId": model["id"],
            "name": model.get("name") or model["id"],
            "owner": _creator(
                model.get("author_info", {}).get("display_name")
                or model.get("author")
                or model.get("owned_by")
                or ""
            ),
            "description": model.get("description", ""),
            "releaseDate": model.get("release_date"),
            "contextSize": model.get("context_size") or model.get("context_length"),
            "capabilities": _capabilities(model),
            "providers": providers,
            "euProviders": providers,
            "default": rates,
            "eu": dict(rates),
            "quantization": None,
            "priceNote": (
                "EUR Router Price published by EUrouter."
                if currency == "EUR"
                else "USD Router Price published by EUrouter and converted with the listed ECB rate."
            ),
        }
        offers.append(offer)
    if not offers:
        raise ValueError("EUrouter has no usable text-output offers")
    return offers


def fetch_ecb_rate() -> dict:
    start = (now_utc().date() - timedelta(days=14)).isoformat()
    source = ECB_URL.format(start=urllib.parse.quote(start))
    rows = list(csv.DictReader(io.StringIO(fetch_bytes(source).decode("utf-8-sig"))))
    observations = []
    for row in rows:
        date_value = row.get("TIME_PERIOD") or row.get("TIME")
        rate_value = row.get("OBS_VALUE") or row.get("OBSERVATION_VALUE")
        if date_value and rate_value:
            observations.append((date_value, _number(rate_value, "ECB rate")))
    if not observations:
        raise ValueError("ECB response has no observations")
    observation_date, usd_per_eur = max(observations)
    return {
        "series": ECB_SERIES,
        "source": source,
        "observationDate": observation_date,
        "usdPerEur": usd_per_eur,
    }


def _openrouter_rates(model: dict, usd_per_eur: float) -> dict:
    return _usd_rates(model, usd_per_eur)


def fetch_openrouter(exchange_rate: dict) -> list[dict]:
    models = _catalog(fetch_json(OPENROUTER_URL), "OpenRouter")
    eu_models = {
        model["id"]: model
        for model in _catalog(fetch_json(OPENROUTER_EU_URL), "OpenRouter EU")
        if model.get("id")
    }
    offers = []
    for model in models:
        if not model.get("id") or not _is_text_output(model):
            continue
        try:
            default = _openrouter_rates(model, exchange_rate["usdPerEur"])
            eu_model = eu_models.get(model["id"])
            eu = _openrouter_rates(eu_model, exchange_rate["usdPerEur"]) if eu_model else None
        except ValueError:
            continue
        offers.append(
            {
                "key": f"openrouter:{model['id']}",
                "router": "openrouter",
                "routerName": "OpenRouter",
                "modelId": model["id"],
                "name": model.get("name") or model["id"],
                "owner": _creator(
                    model["id"].split("/", 1)[0] if "/" in model["id"] else ""
                ),
                "description": model.get("description", ""),
                "releaseDate": model.get("release_date"),
                "contextSize": model.get("context_length"),
                "capabilities": _capabilities(model),
                "providers": [],
                "euProviders": [],
                "default": default,
                "eu": eu,
                "quantization": None,
                "euPlan": "Business or Enterprise",
                "priceNote": "USD Router Price converted with the listed ECB rate.",
            }
        )
    if not offers:
        raise ValueError("OpenRouter has no usable text-output offers")
    return offers


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


def _converted_usd_rates(cost: dict, usd_per_eur: float) -> dict:
    return _usd_rates({"pricing": cost}, usd_per_eur)


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


def _direct_api_offer(
    provider: dict,
    model: dict,
    exchange_rate: dict,
    *,
    price_note: str,
) -> dict:
    rates = _converted_usd_rates(
        {
            "input": model["input"],
            "cache_read": model.get("input_cache"),
            "output": model["output"],
        },
        exchange_rate["usdPerEur"],
    )
    return {
        "key": f"{provider['id']}:{model['id']}",
        "router": provider["id"],
        "routerName": provider["name"],
        "modelId": model["id"],
        "name": model["id"],
        "owner": provider["owner"],
        "description": "",
        "releaseDate": None,
        "contextSize": model.get("context"),
        "capabilities": {
            "reasoning": False,
            "tools": False,
            "vision": False,
            "audio": False,
        },
        "providers": [],
        "euProviders": [],
        "default": rates,
        "eu": None,
        "quantization": None,
        "direct": True,
        "priceNote": price_note,
    }


def _plain_markdown(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _optional_price(value: str) -> float | None:
    return None if value.strip() in {"-", "—", ""} else parse_price(value)


def parse_claude_pricing(markdown: str) -> list[dict]:
    section = markdown.split("## Model pricing", 1)
    if len(section) != 2:
        raise ValueError("Claude pricing page has no model pricing section")
    table = next(
        (
            item
            for item in parse_markdown_tables(section[1])
            if item
            and {"Model", "Base input tokens", "Cache hits and refreshes", "Output tokens"}
            <= set(item[0])
        ),
        None,
    )
    if not table:
        raise ValueError("Claude pricing page has no model pricing table")

    header, *rows = table
    input_index = header.index("Base input tokens")
    cached_index = header.index("Cache hits and refreshes")
    output_index = header.index("Output tokens")
    models = []
    for row in rows:
        name = _plain_markdown(row[0])
        if not name or any(
            marker in name.lower() for marker in ("retired", "limited availability")
        ):
            continue
        name = re.sub(r"\s*\(preview\)\s*$", "", name, flags=re.I)
        model_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        models.append(
            {
                "id": model_id,
                "name": name,
                "input": parse_price(row[input_index]),
                "input_cache": parse_price(row[cached_index]),
                "output": parse_price(row[output_index]),
            }
        )
    if not models:
        raise ValueError("Claude pricing page has no usable models")
    return models


def parse_openai_pricing(markdown: str) -> list[dict]:
    section = markdown.split("### Standard pricing data", 1)
    if len(section) != 2:
        raise ValueError("OpenAI pricing page has no standard pricing section")
    table = parse_markdown_tables(section[1])[0]
    required = {
        "Model",
        "Short context input",
        "Short context cached input",
        "Short context output",
    }
    if not table or not required <= set(table[0]):
        raise ValueError("OpenAI standard pricing table has unexpected columns")

    header, *rows = table
    indexes = {name: header.index(name) for name in required}
    long_indexes = {
        name: header.index(name)
        for name in (
            "Long context input",
            "Long context cached input",
            "Long context output",
        )
        if name in header
    }
    models = []
    for row in rows:
        raw_name = _plain_markdown(row[indexes["Model"]])
        model_id = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name).strip()
        input_rate = _optional_price(row[indexes["Short context input"]])
        output_rate = _optional_price(row[indexes["Short context output"]])
        if not model_id or input_rate is None or output_rate is None:
            continue
        model = {
            "id": model_id,
            "name": model_id,
            "input": input_rate,
            "input_cache": _optional_price(
                row[indexes["Short context cached input"]]
            ),
            "output": output_rate,
        }
        long_input = (
            _optional_price(row[long_indexes["Long context input"]])
            if "Long context input" in long_indexes
            else None
        )
        long_output = (
            _optional_price(row[long_indexes["Long context output"]])
            if "Long context output" in long_indexes
            else None
        )
        if (
            "<272k context length" in raw_name.lower()
            and long_input is not None
            and long_output is not None
        ):
            model["long_context"] = {
                "contextAbove": 272_000,
                "input": long_input,
                "input_cache": _optional_price(
                    row[long_indexes["Long context cached input"]]
                ),
                "output": long_output,
            }
        models.append(model)
    if not models:
        raise ValueError("OpenAI pricing page has no usable text models")
    return models


def _direct_pricing_tiers(model: dict, exchange_rate: dict) -> list[dict]:
    tier = model.get("long_context")
    if not tier:
        return []
    rates = _converted_usd_rates(
        {
            "input": tier["input"],
            "cache_read": tier.get("input_cache"),
            "output": tier["output"],
        },
        exchange_rate["usdPerEur"],
    )
    return [{"contextAbove": tier["contextAbove"], **rates}]


def _direct_api_offers(
    metadata: dict,
    models: list[dict],
    exchange_rate: dict,
    *,
    price_note: str,
) -> list[dict]:
    offers = []
    for model in models:
        offer = _direct_api_offer(
            metadata,
            model,
            exchange_rate,
            price_note=price_note,
        )
        offer["name"] = model.get("name", model["id"])
        offer["pricingTiers"] = _direct_pricing_tiers(model, exchange_rate)
        offers.append(offer)
    return offers


def fetch_claude_direct(exchange_rate: dict) -> list[dict]:
    offers = _direct_api_offers(
        {"id": "claude-direct", "name": "Claude API", "owner": "Anthropic"},
        parse_claude_pricing(fetch_text(CLAUDE_PRICING_URL)),
        exchange_rate,
        price_note=(
            "Direct USD API price published by Anthropic and converted with the "
            "listed ECB rate. This is not a routed offer."
        ),
    )
    if not offers:
        raise ValueError("Claude API has no usable offers")
    return offers


def fetch_openai_direct(exchange_rate: dict) -> list[dict]:
    offers = _direct_api_offers(
        {"id": "openai-direct", "name": "OpenAI API", "owner": "OpenAI"},
        parse_openai_pricing(fetch_text(OPENAI_PRICING_URL)),
        exchange_rate,
        price_note=(
            "Direct USD standard API price published by OpenAI and converted "
            "with the listed ECB rate. This is not a routed offer."
        ),
    )
    if not offers:
        raise ValueError("OpenAI API has no usable offers")
    return offers


def fetch_deepseek_direct(exchange_rate: dict) -> list[dict]:
    provider = scrape_deepseek()
    metadata = {"id": "deepseek-direct", "name": "DeepSeek API", "owner": "DeepSeek"}
    offers = [
        _direct_api_offer(
            metadata,
            model,
            exchange_rate,
            price_note=(
                "Direct USD API peak price published by DeepSeek and converted "
                "with the listed ECB rate. This is not a routed offer."
            ),
        )
        for model in provider["models"]
    ]
    if not offers:
        raise ValueError("DeepSeek API has no usable offers")
    return offers


def fetch_zai_direct(exchange_rate: dict) -> list[dict]:
    provider = scrape_zai_paygo()
    metadata = {"id": "zai-direct", "name": "z.ai API", "owner": "Z.ai"}
    offers = [
        _direct_api_offer(
            metadata,
            model,
            exchange_rate,
            price_note=(
                "Direct USD API price published by z.ai and converted with the "
                "listed ECB rate. This is not a routed offer."
            ),
        )
        for model in provider["models"]
    ]
    if not offers:
        raise ValueError("z.ai API has no usable offers")
    return offers


ROUTERS = {
    "cortecs": {
        "name": "Cortecs",
        "source": CORTECS_URL,
        "euClaim": "EU catalog: providers based and regulated within the EU.",
    },
    "eurouter": {
        "name": "EUrouter",
        "source": EUROUTER_URL,
        "euClaim": "EU handling is EUrouter's baseline routing guarantee.",
    },
    "openrouter": {
        "name": "OpenRouter",
        "source": OPENROUTER_URL,
        "euClaim": "EU regional routing; Business or Enterprise plan required.",
    },
    "opencode": {
        "name": "OpenCode Zen",
        "source": OPENCODE_ZEN_URL,
        "euClaim": "No EU routing catalog is published.",
    },
    "deepseek-direct": {
        "name": "DeepSeek API",
        "source": DEEPSEEK_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "zai-direct": {
        "name": "z.ai API",
        "source": ZAI_PAYGO_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "claude-direct": {
        "name": "Claude API",
        "source": CLAUDE_PRICING_URL,
        "catalogSource": CLAUDE_MODELS_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "openai-direct": {
        "name": "OpenAI API",
        "source": OPENAI_PRICING_URL,
        "catalogSource": OPENAI_MODELS_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _cached_router(previous: dict, router_id: str, error: Exception, fetched_at: str):
    metadata = next(
        (router for router in previous.get("routers", []) if router.get("id") == router_id),
        None,
    )
    offers = [
        offer for offer in previous.get("offers", []) if offer.get("router") == router_id
    ]
    if not metadata or not offers:
        return None
    original_time = metadata.get("fetchedAt")
    if not original_time or now_utc() - _parse_time(original_time) > MAX_STALE_AGE:
        return None
    return (
        {
            **ROUTERS[router_id],
            "id": router_id,
            "fetchedAt": original_time,
            "stale": True,
            "error": str(error),
            "fallbackAttemptedAt": fetched_at,
        },
        offers,
    )


def build(previous: dict | None = None) -> dict:
    previous = previous or {}
    generated = now_utc().isoformat()
    routers = []
    offers = []
    omitted = []

    exchange_rate = None
    ecb_error = None
    try:
        exchange_rate = fetch_ecb_rate()
    except Exception as error:
        ecb_error = error
        exchange_rate = previous.get("exchangeRate")

    adapters = {
        "cortecs": fetch_cortecs,
        "eurouter": lambda: fetch_eurouter(exchange_rate),
    }
    if exchange_rate and not ecb_error:
        adapters["openrouter"] = lambda: fetch_openrouter(exchange_rate)
        adapters["opencode"] = lambda: fetch_opencode(exchange_rate)
        adapters["deepseek-direct"] = lambda: fetch_deepseek_direct(exchange_rate)
        adapters["zai-direct"] = lambda: fetch_zai_direct(exchange_rate)
        adapters["claude-direct"] = lambda: fetch_claude_direct(exchange_rate)
        adapters["openai-direct"] = lambda: fetch_openai_direct(exchange_rate)
    elif ecb_error:
        def unavailable_openrouter():
            raise RuntimeError(f"ECB: {ecb_error}")

        adapters["openrouter"] = unavailable_openrouter
        adapters["opencode"] = unavailable_openrouter
        adapters["deepseek-direct"] = unavailable_openrouter
        adapters["zai-direct"] = unavailable_openrouter
        adapters["claude-direct"] = unavailable_openrouter
        adapters["openai-direct"] = unavailable_openrouter

    for router_id, adapter in adapters.items():
        try:
            router_offers = adapter()
            routers.append(
                {
                    **ROUTERS[router_id],
                    "id": router_id,
                    "fetchedAt": generated,
                    "stale": False,
                }
            )
            offers.extend(router_offers)
        except Exception as error:
            cached = _cached_router(previous, router_id, error, generated)
            if cached:
                metadata, router_offers = cached
                routers.append(metadata)
                offers.extend(router_offers)
                if router_id in {
                    "openrouter",
                    "opencode",
                    "deepseek-direct",
                    "zai-direct",
                    "claude-direct",
                    "openai-direct",
                }:
                    exchange_rate = previous.get("exchangeRate")
            else:
                omitted.append({"id": router_id, "reason": str(error)})

    if not offers:
        reasons = "; ".join(f"{item['id']}: {item['reason']}" for item in omitted)
        raise RuntimeError(f"no router data is usable ({reasons})")

    return {
        "schemaVersion": 1,
        "generatedAt": generated,
        "currency": "EUR",
        "exchangeRate": exchange_rate,
        "routers": routers,
        "omittedRouters": omitted,
        "offers": sorted(offers, key=lambda offer: offer["key"]),
    }


def main() -> None:
    previous = None
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    output = build(previous)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    counts = {
        router["id"]: sum(offer["router"] == router["id"] for offer in output["offers"])
        for router in output["routers"]
    }
    print(f"Wrote {OUTPUT_PATH}: {counts}")
    for omitted in output["omittedRouters"]:
        print(f"Warning: omitted {omitted['id']}: {omitted['reason']}")


if __name__ == "__main__":
    main()
