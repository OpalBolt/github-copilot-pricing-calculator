"""Claude direct API adapter: parses Anthropic's published pricing page."""

from fetch_providers import fetch_text
from sources.helpers import _direct_api_offers, listing_from_offer, parse_claude_pricing

CLAUDE_MODELS_URL = "https://platform.claude.com/docs/en/api/http/beta/models/list.md"
CLAUDE_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"


def fetch_claude_direct_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Anthropic's first-party prices."""
    return [
        listing_from_offer(
            offer,
            price_note=(
                "Direct USD API price published by Anthropic and converted "
                "with the listed ECB rate."
            ),
        )
        for offer in fetch_claude_direct(exchange_rate)
    ]


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
