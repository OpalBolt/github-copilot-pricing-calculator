"""Mistral direct API adapter: parses Mistral's published pricing markdown."""

import re

from fetch_providers import fetch_text, parse_markdown_tables
from sources.helpers import (
    _creator,
    _direct_api_offers,
    _plain_markdown,
    listing_from_offer,
)

MISTRAL_PRICING_URL = "https://docs.mistral.ai/inference/pricing.md"

# Mistral's regional-inference doc bills its EU endpoint at "1.1× standard
# list pricing (a 10% upcharge) for input tokens, output tokens, cached
# reads, and cache writes"
# (docs.mistral.ai/inference/regional-inference).
EU_LIST_MULTIPLIER = 1.1

# Every section's table prices one model per row, with the Price cell
# joining rate lines on <br>: "Input $0.68 /M Tokens (sale price, regular
# $1.36)". The line's own number is the advertised sale price and the
# "regular" number is the list price the calculator headlines.
_RATE_LINE = re.compile(
    r"^(?P<label>Input|Cached input|Output)?\s*"
    r"\$(?P<price>[0-9]+(?:\.[0-9]+)?)\s+/M Tokens"
    r"(?:\s*\(sale price, regular \$(?P<regular>[0-9]+(?:\.[0-9]+)?)\))?$"
)
_RATE_FIELDS = {
    "Input": "input",
    "Cached input": "input_cache",
    "Output": "output",
}


def _rates_from_cell(cell: str) -> dict | None:
    """The per-million-token rates in one Price cell: the regular price is
    the headline, an advertised sale price rides along in `sale`, and
    per-page, per-minute, and per-character lines never match. The
    moderation row publishes "Free" with one unlabeled "$0 /M Tokens"
    rate — the free model bills nothing in either direction, so the
    published zero covers input and output; an unlabeled rate without the
    Free marker has no direction to attach to and skips the row."""
    input_rate = cached_rate = output_rate = None
    bare = None
    sale: dict[str, float] = {}
    for line in cell.split("<br>"):
        match = _RATE_LINE.match(_plain_markdown(line))
        if not match:
            continue
        price = float(match["price"])
        label = match["label"]
        if label is None:
            bare = price
            continue
        if match["regular"] is not None:
            sale[_RATE_FIELDS[label]] = price
            price = float(match["regular"])
        if label == "Input":
            input_rate = price
        elif label == "Cached input":
            cached_rate = price
        else:
            output_rate = price
    if input_rate is None or output_rate is None:
        if bare is None or not re.search(r"\bfree\b", cell, re.IGNORECASE):
            return None
        input_rate = output_rate = bare
    rates = {
        "input": input_rate,
        "input_cache": cached_rate,
        "output": output_rate,
    }
    if sale:
        rates["sale"] = sale
    return rates


def parse_mistral_pricing(markdown: str) -> list[dict]:
    """Mistral's published per-million-token API rates: one entry per
    model, headlined at the regular price with any advertised sale price
    alongside. Per-page, per-minute, and per-character rows are not token
    pricing and stay out rather than broken. The markdown's own
    "Third-party hosted" section marks models Mistral serves for another
    operator, so those entries carry that operator's owner alias."""
    columns = {"Model", "API name", "Price"}
    models = []
    for block in re.split(r"^## ", markdown, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        owner = "zai" if heading.strip() == "Third-party hosted" else "mistralai"
        table = next(
            (
                item
                for item in parse_markdown_tables(body)
                if item and columns <= set(item[0])
            ),
            None,
        )
        if not table:
            continue
        header, *rows = table
        indexes = {name: header.index(name) for name in columns}
        for row in rows:
            name = _plain_markdown(row[indexes["Model"]])
            model_id = row[indexes["API name"]].strip().strip("`")
            rates = _rates_from_cell(row[indexes["Price"]])
            if not name or not model_id or rates is None:
                continue
            models.append({"id": model_id, "name": name, "owner": owner, **rates})
    if not models:
        raise ValueError("Mistral pricing page has no usable text models")
    return models


def _sale_note(sale: dict) -> str:
    """The advertised sale prices for the price note, in the note's field
    order."""
    labels = {"input": "input", "input_cache": "cached input", "output": "output"}
    parts = [
        f"${sale[field]:g} {labels[field]}"
        for field in ("input", "input_cache", "output")
        if field in sale
    ]
    return (
        " Mistral currently advertises a sale price of "
        f"{' / '.join(parts)} per million tokens."
    )


def _eu_regional_rates(default: dict, usd_per_eur: float) -> dict:
    """The EU regional endpoint's rates for one offer: the native USD list
    rates × the 1.1× regional upcharge, converted with the shared ECB rate
    (EUR = native × 1.1 / usdPerEur). Free rows' zeros stay zero (0 × 1.1 =
    0), and a cached-input fallback keeps estimating cache reads at the
    equally multiplied input rate."""
    native = {
        field: value * EU_LIST_MULTIPLIER
        for field, value in default["native"].items()
    }
    return {
        "input": native["input"] / usd_per_eur,
        "cached": native["cached"] / usd_per_eur,
        "output": native["output"] / usd_per_eur,
        "cachedFallback": default["cachedFallback"],
        "nativeCurrency": "USD",
        "native": native,
    }


def fetch_mistral_direct(exchange_rate: dict) -> list[dict]:
    """EU-page Router Offers: Mistral AI's own API as an EU-claiming seller.
    The default mode carries the standard list prices the global listings
    headline; the EU mode prices the EU regional endpoint
    (api.eu.mistral.ai), which bills inference in EU/EFTA data centers at
    the 1.1× list upcharge computed from the native USD rates. The
    regional-inference doc only serves "models hosted in that region" with
    no stateful features, so the price note carries those caveats, and the
    sale-price discipline matches the listings path: the regular price is
    the headline and any advertised sale price stays in the price note."""
    models = parse_mistral_pricing(fetch_text(MISTRAL_PRICING_URL))
    base_note = (
        "Direct USD API price published by Mistral AI and converted with "
        "the listed ECB rate. EU prices apply the EU regional endpoint's "
        "1.1× list upcharge; regional endpoints only serve models hosted "
        "in that region, and stateful features (Agents, Batch, Files) are "
        "unavailable there."
    )
    offers = _direct_api_offers(
        {"id": "mistral", "name": "Mistral AI", "owner": "mistralai"},
        models,
        exchange_rate,
        price_note=base_note,
    )
    if not offers:
        raise ValueError("Mistral API has no usable offers")
    usd_per_eur = exchange_rate["usdPerEur"]
    for model, offer in zip(models, offers):
        # Third-party hosted rows carry the model operator's own canonical
        # owner name; the seller stays Mistral AI either way.
        offer["owner"] = _creator(model["owner"])
        if model.get("sale"):
            offer["priceNote"] = base_note + _sale_note(model["sale"])
        offer["eu"] = _eu_regional_rates(offer["default"], usd_per_eur)
    return offers


def fetch_mistral_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Mistral AI's first-party prices. The
    regular price is the headline; an advertised sale price is named in
    the price note rather than headlined."""
    models = parse_mistral_pricing(fetch_text(MISTRAL_PRICING_URL))
    base_note = (
        "Direct USD API price published by Mistral AI and converted with "
        "the listed ECB rate."
    )
    offers = _direct_api_offers(
        {"id": "mistral", "name": "Mistral AI", "owner": "mistralai"},
        models,
        exchange_rate,
        price_note=base_note,
    )
    if not offers:
        raise ValueError("Mistral API has no usable offers")
    listings = []
    for model, offer in zip(models, offers):
        # Third-party hosted rows carry the model operator's own owner
        # alias; the seller stays Mistral AI either way.
        offer["owner"] = model["owner"]
        price_note = (
            base_note + _sale_note(model["sale"])
            if model.get("sale")
            else base_note
        )
        listings.append(listing_from_offer(offer, price_note=price_note))
    return listings
