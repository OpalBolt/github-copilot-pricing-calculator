"""Meta direct API adapter: parses Meta's published pricing markdown."""

import re

from fetch_providers import fetch_text, parse_markdown_tables
from sources.helpers import (
    _direct_api_offers,
    _plain_markdown,
    listing_from_offer,
)

META_PRICING_URL = "https://dev.meta.ai/docs/pricing-rate-limits.md"

# The token-pricing tables read one rate direction per Usage row and one
# pricing mode per column, and both mode columns bill per million tokens.
_MODE_COLUMNS = {
    "standard": "Standard mode (per 1M tokens)",
    "contributor": "Contributor mode (per 1M tokens)",
}
_USAGE_FIELDS = {
    "Cached input": "input_cache",
    "Input": "input",
    "Output": "output",
}
_DOLLAR_PRICE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)")


def _mode_rates(mode_column: str, rows: list[list[str]], indexes: dict) -> dict:
    """One mode column's rates keyed by rate direction; a cell without a
    dollar price ("Not available") leaves that mode without that rate."""
    rates = {}
    index = indexes[mode_column]
    for row in rows:
        field = _USAGE_FIELDS.get(_plain_markdown(row[indexes["Usage"]]))
        match = (
            _DOLLAR_PRICE.fullmatch(row[index].strip()) if field else None
        )
        if match:
            rates[field] = float(match.group(1))
    return rates


def parse_meta_pricing(markdown: str) -> list[dict]:
    """Meta's published per-million-token API rates: one entry per
    Standard-mode model id, headlined at the Standard-mode price with the
    Contributor-mode discount alongside. The Contributor-mode ids
    (`*-contributor`) are the same models at the discounted rate, so they
    stay inside the entry's `contributor` rates instead of becoming
    separate listings. Muse Image, Muse Voice Transcribe, and SAM price
    images, audio hours, and frames rather than tokens, and the prose
    mode sections price nothing, so their sections stay out rather than
    broken."""
    columns = {"Usage", *_MODE_COLUMNS.values()}
    models = []
    for block in re.split(r"^### ", markdown, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
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
        standard = _mode_rates(_MODE_COLUMNS["standard"], rows, indexes)
        if "input" not in standard or "output" not in standard:
            continue
        contributor = _mode_rates(
            _MODE_COLUMNS["contributor"], rows, indexes
        )
        # The section prose names the model ids in backticks; an id ending
        # in `-contributor` is the Contributor-mode variant of the
        # Standard-mode model of the same name, so only models with their
        # own variant carry the discount.
        prose = body.split("\n|", 1)[0]
        ids = re.findall(r"`([^`]+)`", prose)
        variants = {
            model_id[: -len("-contributor")]
            for model_id in ids
            if model_id.endswith("-contributor")
        }
        for model_id in ids:
            if model_id.endswith("-contributor"):
                continue
            model = {
                "id": model_id,
                "name": heading.strip(),
                "input": standard["input"],
                "input_cache": standard.get("input_cache"),
                "output": standard["output"],
            }
            if model_id in variants and contributor:
                model["contributor"] = contributor
            models.append(model)
    if not models:
        raise ValueError("Meta pricing page has no usable text models")
    return models


def _contributor_note(model: dict) -> str:
    """The Contributor-mode discount for the price note, in the note's
    field order."""
    labels = {"input": "input", "input_cache": "cached input", "output": "output"}
    parts = [
        f"${model['contributor'][field]:g} {labels[field]}"
        for field in ("input", "input_cache", "output")
        if field in model["contributor"]
    ]
    return (
        f" Meta's Contributor mode bills the same model as"
        f" `{model['id']}-contributor` at {' / '.join(parts)} per million"
        " tokens, in exchange for permission to use sent content to train"
        " future Meta models."
    )


def fetch_meta_listings(exchange_rate: dict) -> list[dict]:
    """Global-page Model Listings: Meta's first-party prices. The
    Standard-mode price is the headline; the Contributor-mode discount is
    named in the price note rather than headlined."""
    models = parse_meta_pricing(fetch_text(META_PRICING_URL))
    base_note = (
        "Direct USD API price published by Meta and converted with the "
        "listed ECB rate."
    )
    offers = _direct_api_offers(
        {"id": "meta", "name": "Meta", "owner": "meta"},
        models,
        exchange_rate,
        price_note=base_note,
    )
    if not offers:
        raise ValueError("Meta API has no usable offers")
    return [
        listing_from_offer(
            offer,
            price_note=(
                base_note + _contributor_note(model)
                if model.get("contributor")
                else base_note
            ),
        )
        for model, offer in zip(models, offers)
    ]
