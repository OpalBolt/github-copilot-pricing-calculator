"""DeepSeek direct API adapter: pay-as-you-go prices scraped from the docs."""

from fetch_providers import scrape_deepseek
from sources.helpers import _direct_api_offer


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
