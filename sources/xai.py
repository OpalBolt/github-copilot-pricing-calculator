"""xAI direct API adapter: parses xAI's published pricing markdown."""

import re

from fetch_providers import fetch_text, parse_context_len, parse_markdown_tables
from sources.helpers import (
    _direct_api_offers,
    _optional_price,
    _plain_markdown,
    listing_from_offer,
)

XAI_PRICING_URL = "https://docs.x.ai/developers/pricing.md"

# The text-API table splits long-context models into two rows: the
# short-context headline row "(< 200k prompt tokens)" and the tier row
# "(≥ 200k prompt tokens)" whose rates apply once the prompt reaches the
# threshold. Thresholds reuse the openai-direct convention (272k -> 272_000).
_TIER_MARKER = re.compile(
    r"\((<|≥)\s*([0-9]+(?:\.[0-9]+)?)\s*([km]) prompt tokens\)\s*$",
    re.IGNORECASE,
)


def _threshold_tokens(number: str, unit: str) -> int:
    return int(float(number) * {"k": 1_000, "m": 1_000_000}[unit.lower()])


def _context_tokens(value: str) -> int | None:
    """The published Context shorthand ("500k", "1M") through the shared
    context parser; anything else stays unpublished."""
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\s*[km]?", value.strip(), re.I):
        return None
    return parse_context_len(value)


def parse_xai_pricing(markdown: str) -> list[dict]:
    """The published text-API rates: one entry per model with the
    short-context headline rates and any long-context tier, all USD per
    million tokens as published. Imagine, voice, and tool tables price
    something other than tokens, and rows without token pricing are skipped
    rather than broken."""
    section = markdown.split("### Text API Pricing", 1)
    if len(section) != 2:
        raise ValueError("xAI pricing page has no text API pricing section")
    columns = {
        "Model",
        "Input / 1M tokens",
        "Cached input / 1M tokens",
        "Output / 1M tokens",
    }
    table = next(
        (
            item
            for item in parse_markdown_tables(section[1])
            if item and columns <= set(item[0])
        ),
        None,
    )
    if not table:
        raise ValueError("xAI pricing page has no text API pricing table")

    header, *rows = table
    indexes = {name: header.index(name) for name in columns}
    context_index = header.index("Context") if "Context" in header else None

    def row_rates(row: list[str]) -> dict | None:
        input_rate = _optional_price(row[indexes["Input / 1M tokens"]])
        output_rate = _optional_price(row[indexes["Output / 1M tokens"]])
        if input_rate is None or output_rate is None:
            return None
        return {
            "input": input_rate,
            "input_cache": _optional_price(
                row[indexes["Cached input / 1M tokens"]]
            ),
            "output": output_rate,
        }

    models: dict[str, dict] = {}
    for row in rows:
        raw_name = _plain_markdown(row[indexes["Model"]])
        marker = _TIER_MARKER.search(raw_name)
        rates = row_rates(row)
        if not raw_name or rates is None:
            continue
        model_id = raw_name[: marker.start()].strip() if marker else raw_name
        if marker and marker.group(1) == "≥":
            # The tier row completes the model's short-context row; a tier
            # without a headline row has no listing to attach to.
            if model_id in models:
                models[model_id]["long_context"] = {
                    "contextAbove": _threshold_tokens(*marker.group(2, 3)),
                    **rates,
                }
            continue
        models[model_id] = {
            "id": model_id,
            "name": model_id,
            "context": (
                _context_tokens(row[context_index])
                if context_index is not None
                else None
            ),
            **rates,
        }
    if not models:
        raise ValueError("xAI pricing page has no usable text models")
    return list(models.values())


def fetch_xai_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: xAI's first-party prices."""
    offers = _direct_api_offers(
        {"id": "xai", "name": "xAI", "owner": "xAI"},
        parse_xai_pricing(fetch_text(XAI_PRICING_URL)),
        exchange_rate,
        price_note=(
            "Direct USD API price published by xAI and converted with the "
            "listed ECB rate. This is not a routed offer."
        ),
    )
    if not offers:
        raise ValueError("xAI API has no usable offers")
    return [
        listing_from_offer(
            offer,
            price_note=(
                "Direct USD API price published by xAI and converted with "
                "the listed ECB rate."
            ),
        )
        for offer in offers
    ]
