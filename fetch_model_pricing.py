#!/usr/bin/env python3
"""Build the global Model Price Calculator dataset from the registered
sources.

Thin per-page build step: one ECB rate fetch shared by all adapters, each
source fetched once, per-source failure isolation, and the seven-day stale
rule. Mirrors fetch_router_pricing.py; selects the registry's `global` pages
and writes one Model Listing per catalog row.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from sources import SOURCES
from sources.claude_direct import fetch_claude_direct_listings
from sources.cortecs import fetch_cortecs_listings
from sources.deepinfra import fetch_deepinfra_listings
from sources.deepseek_direct import fetch_deepseek_direct_listings
from sources.eurouter import fetch_eurouter_listings
from sources.helpers import fetch_ecb_rate, now_utc
from sources.kilo import fetch_kilo_listings
from sources.nano_gpt import fetch_nano_gpt_listings
from sources.novita import fetch_novita_listings
from sources.openai_direct import fetch_openai_direct_listings
from sources.opencode import fetch_opencode_listings
from sources.openrouter import fetch_openrouter_listings
from sources.requesty import fetch_requesty_listings
from sources.vercel_gateway import fetch_vercel_gateway_listings
from sources.zai_direct import fetch_zai_direct_listings

ROOT = Path(__file__).parent
OUTPUT_PATH = ROOT / "model-pricing.json"
MAX_STALE_AGE = timedelta(days=7)

# This page's registry key and one listings adapter per selected source.
# Sources are chosen through the registry's `pages` field in build(); on day
# one every registered source declares `global`. Each lambda resolves its
# fetch function at call time so tests can patch the module attribute.
GLOBAL_PAGE = "global"
ADAPTERS = {
    "cortecs": lambda _exchange_rate: fetch_cortecs_listings(),
    "eurouter": lambda exchange_rate: fetch_eurouter_listings(exchange_rate),
    "openrouter": lambda exchange_rate: fetch_openrouter_listings(exchange_rate),
    "opencode": lambda exchange_rate: fetch_opencode_listings(exchange_rate),
    "deepinfra": lambda exchange_rate: fetch_deepinfra_listings(exchange_rate),
    "novita": lambda exchange_rate: fetch_novita_listings(exchange_rate),
    "requesty": lambda exchange_rate: fetch_requesty_listings(exchange_rate),
    "nano-gpt": lambda exchange_rate: fetch_nano_gpt_listings(exchange_rate),
    "vercel-gateway": lambda exchange_rate: fetch_vercel_gateway_listings(
        exchange_rate
    ),
    "kilo": lambda exchange_rate: fetch_kilo_listings(exchange_rate),
    "deepseek-direct": lambda exchange_rate: fetch_deepseek_direct_listings(
        exchange_rate
    ),
    "zai-direct": lambda exchange_rate: fetch_zai_direct_listings(exchange_rate),
    "claude-direct": lambda exchange_rate: fetch_claude_direct_listings(exchange_rate),
    "openai-direct": lambda exchange_rate: fetch_openai_direct_listings(exchange_rate),
}
# Sources that still produce listings when the ECB rate fetch fails.
RATE_OPTIONAL_SOURCES = {"cortecs", "eurouter"}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seller_metadata(source_id: str) -> dict:
    """One source's registry metadata without the registry-only `pages` field
    and the EU page's `euClaim` copy, `kind` baseline marker, and
    `catalogSource` pointer."""
    return {
        key: value
        for key, value in SOURCES[source_id].items()
        if key not in {"pages", "euClaim", "kind", "catalogSource"}
    }


def _native_currency(listings: list[dict]) -> str:
    """The seller's catalog currency: the one currency its listings quote, or
    "mixed" when it publishes more than one."""
    currencies = {listing["rates"]["nativeCurrency"] for listing in listings}
    return currencies.pop() if len(currencies) == 1 else "mixed"


def _cached_seller(previous: dict, seller_id: str, error: Exception, fetched_at: str):
    metadata = next(
        (
            seller
            for seller in previous.get("sellers", [])
            if seller.get("id") == seller_id
        ),
        None,
    )
    listings = [
        listing
        for listing in previous.get("listings", [])
        if listing.get("seller") == seller_id
    ]
    if not metadata or not listings:
        return None
    original_time = metadata.get("fetchedAt")
    if not original_time or now_utc() - _parse_time(original_time) > MAX_STALE_AGE:
        return None
    return (
        {
            **_seller_metadata(seller_id),
            "id": seller_id,
            "fetchedAt": original_time,
            "stale": True,
            "error": str(error),
            "fallbackAttemptedAt": fetched_at,
        },
        listings,
    )


def build(previous: dict | None = None) -> dict:
    previous = previous or {}
    generated = now_utc().isoformat()
    sellers = []
    listings = []
    omitted = []

    exchange_rate = None
    ecb_error = None
    try:
        exchange_rate = fetch_ecb_rate()
    except Exception as error:
        ecb_error = error
        exchange_rate = previous.get("exchangeRate")

    adapters = {}
    for source_id, metadata in SOURCES.items():
        if GLOBAL_PAGE not in metadata["pages"]:
            continue
        if ecb_error and source_id not in RATE_OPTIONAL_SOURCES:

            def unavailable(error=ecb_error):
                raise RuntimeError(f"ECB: {error}")

            adapters[source_id] = unavailable
        else:
            adapters[source_id] = lambda sid=source_id: ADAPTERS[sid](exchange_rate)

    for seller_id, adapter in adapters.items():
        try:
            seller_listings = adapter()
            sellers.append(
                {
                    **_seller_metadata(seller_id),
                    "id": seller_id,
                    "nativeCurrency": _native_currency(seller_listings),
                    "fetchedAt": generated,
                    "stale": False,
                }
            )
            listings.extend(seller_listings)
        except Exception as error:
            cached = _cached_seller(previous, seller_id, error, generated)
            if cached:
                metadata, seller_listings = cached
                sellers.append(metadata)
                listings.extend(seller_listings)
                if seller_id not in RATE_OPTIONAL_SOURCES:
                    exchange_rate = previous.get("exchangeRate")
            else:
                omitted.append({"id": seller_id, "reason": str(error)})

    if not listings:
        reasons = "; ".join(f"{item['id']}: {item['reason']}" for item in omitted)
        raise RuntimeError(f"no model pricing data is usable ({reasons})")

    return {
        "schemaVersion": 1,
        "generatedAt": generated,
        "currency": "EUR",
        "exchangeRate": exchange_rate,
        "sellers": sellers,
        "omittedSellers": omitted,
        "listings": sorted(listings, key=lambda listing: listing["key"]),
    }


def main() -> None:
    previous = None
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    output = build(previous)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    counts = {
        seller["id"]: sum(
            listing["seller"] == seller["id"] for listing in output["listings"]
        )
        for seller in output["sellers"]
    }
    print(f"Wrote {OUTPUT_PATH}: {counts}")
    for omitted in output["omittedSellers"]:
        print(f"Warning: omitted {omitted['id']}: {omitted['reason']}")


if __name__ == "__main__":
    main()
