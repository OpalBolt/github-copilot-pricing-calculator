"""OpenAI direct API adapter: parses OpenAI's published pricing page."""

from fetch_providers import fetch_text
from sources.helpers import _direct_api_offers, parse_openai_pricing

OPENAI_MODELS_URL = (
    "https://developers.openai.com/api/reference/resources/models/methods/list"
)
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"


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
