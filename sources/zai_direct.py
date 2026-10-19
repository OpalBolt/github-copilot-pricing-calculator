"""z.ai direct API adapter: pay-as-you-go prices scraped from the docs."""

from fetch_providers import scrape_zai_paygo
from sources.helpers import _direct_api_offer


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
