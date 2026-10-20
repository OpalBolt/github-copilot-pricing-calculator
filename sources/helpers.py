"""Shared helpers for the pricing source adapters: fetching, rate
normalization, EUR conversion, capability derivation, canonical organization
names, and the pricing-page parsers."""

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fetch_providers import parse_markdown_tables, parse_price

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
    # spill: slice 04 — DeepInfra ids use the `deepseek-ai/` prefix.
    "deepseekai": "DeepSeek",
    # spill: slice 24 — Pioneer (Fastino) rows name their own models'
    # operator `fastino` in owned_by.
    "fastino": "Fastino",
    # spill: slice 15 — Crossmodel ids use the `gemini/` prefix for Google
    # models.
    "gemini": "Google",
    "google": "Google",
    "meta": "Meta",
    "metaai": "Meta",
    "metallama": "Meta",
    "minimax": "MiniMax AI",
    "minimaxai": "MiniMax AI",
    "mistralai": "Mistral AI",
    # spill: slice 06 — Requesty's `model_lab` uses these shorter spellings.
    "mistral": "Mistral AI",
    "moonshot": "Moonshot AI",
    "moonshotai": "Moonshot AI",
    "nousresearch": "Nous Research",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "qwen": "Alibaba",
    # spill: slice 05 — Novita ids use the `sao10k/` prefix in both cases.
    "sao10k": "Sao10K",
    # spill: slice 23 — OfoxAI's Doubao rows name their serving platform
    # `volcengine` (ByteDance's cloud) as owned_by.
    "volcengine": "ByteDance",
    "xiaomi": "Xiaomi",
    # spill: slice 05 — Novita ids use the `xiaomimimo/` prefix.
    "xiaomimimo": "XiaomiMiMo",
    "xai": "xAI",
    "zai": "Z.ai",
    # spill: slice 04 — DeepInfra ids use the `zai-org/` prefix.
    "zaiorg": "Z.ai",
    "zhipu": "Z.ai",
    "zhipuai": "Z.ai",
}

PROVIDER_ALIASES = {
    "entrim": "Entrim",
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


def _converted_usd_rates(cost: dict, usd_per_eur: float) -> dict:
    return _usd_rates({"pricing": cost}, usd_per_eur)


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


def listing_from_offer(offer: dict, price_note: str | None = None) -> dict:
    """One Model Listing for the global page, built from the shared fetch
    layer's offer: EU-page fields (routing modes, EU providers, quantization)
    are dropped, seller fields are renamed, the canonical creator is reused,
    and the native rates are always explicit next to the EUR conversion."""
    rates = offer["default"]
    native = rates.get("native") or {
        field: rates[field] for field in ("input", "cached", "output")
    }
    return {
        "key": offer["key"],
        "seller": offer["router"],
        "sellerName": offer["routerName"],
        "modelId": offer["modelId"],
        "name": offer["name"],
        "creator": _creator(offer.get("owner")),
        "description": offer.get("description", ""),
        "releaseDate": offer.get("releaseDate"),
        "contextSize": offer.get("contextSize"),
        "capabilities": offer.get("capabilities")
        or {"reasoning": False, "tools": False, "vision": False, "audio": False},
        "rates": {**rates, "native": native},
        "pricingTiers": offer.get("pricingTiers", []),
        "priceNote": price_note or offer["priceNote"],
    }


def dedupe_identical_listings(listings: list[dict]) -> list[dict]:
    """One seller's listings with identical variant rows collapsed: the same
    model reached through several upstream routes at one price renders as
    visually identical duplicate rows, so only the first variant in listing
    order survives (the edenai adapter's first-wins precedent). Variants
    differing in display name, creator, or any EUR rate are genuine distinct
    offers (confidential-compute and discount rows) and stay."""
    seen: set[tuple] = set()
    surviving = []
    for listing in listings:
        identity = (
            listing["name"],
            listing["creator"],
            listing["rates"]["input"],
            listing["rates"]["cached"],
            listing["rates"]["output"],
        )
        if identity not in seen:
            seen.add(identity)
            surviving.append(listing)
    return surviving


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
