#!/usr/bin/env python3
"""Build the EU router page dataset from the registered pricing sources.

Thin per-page build step: one ECB rate fetch shared by all adapters, each
source fetched once, per-source failure isolation, and the seven-day stale
rule.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from sources import SOURCES
from sources.claude_direct import fetch_claude_direct
from sources.cortecs import fetch_cortecs
from sources.deepseek_direct import fetch_deepseek_direct
from sources.eurouter import fetch_eurouter
from sources.helpers import fetch_ecb_rate, now_utc
from sources.mistral import fetch_mistral_direct
from sources.openai_direct import fetch_openai_direct
from sources.openrouter import fetch_openrouter
from sources.zai_direct import fetch_zai_direct

ROOT = Path(__file__).parent
OUTPUT_PATH = ROOT / "eu-router-pricing.json"
MAX_STALE_AGE = timedelta(days=7)

# This page's registry key and one adapter per selected source. Sources are
# chosen through the registry's `pages` field in build(); OpenCode Zen is
# absent because its registry `pages` is global-only. Each lambda resolves
# its fetch function at call time so tests can patch the module attribute.
ROUTER_PAGE = "router"
ADAPTERS = {
    "cortecs": lambda _exchange_rate: fetch_cortecs(),
    "eurouter": lambda exchange_rate: fetch_eurouter(exchange_rate),
    "openrouter": lambda exchange_rate: fetch_openrouter(exchange_rate),
    "deepseek-direct": lambda exchange_rate: fetch_deepseek_direct(exchange_rate),
    "zai-direct": lambda exchange_rate: fetch_zai_direct(exchange_rate),
    "claude-direct": lambda exchange_rate: fetch_claude_direct(exchange_rate),
    "openai-direct": lambda exchange_rate: fetch_openai_direct(exchange_rate),
    "mistral": lambda exchange_rate: fetch_mistral_direct(exchange_rate),
}
# Sources that still produce offers when the ECB rate fetch fails.
RATE_OPTIONAL_SOURCES = {"cortecs", "eurouter"}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _router_metadata(source_id: str) -> dict:
    """One source's registry metadata without the registry-only `pages` field."""
    # spill: slice 03 added `sellerKind` for the global page; the EU dataset
    # must stay unchanged, so the EU build drops that field here.
    return {
        key: value
        for key, value in SOURCES[source_id].items()
        if key not in {"pages", "sellerKind"}
    }


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
            **_router_metadata(router_id),
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

    adapters = {}
    for source_id, metadata in SOURCES.items():
        if ROUTER_PAGE not in metadata["pages"]:
            continue
        if ecb_error and source_id not in RATE_OPTIONAL_SOURCES:

            def unavailable(error=ecb_error):
                raise RuntimeError(f"ECB: {error}")

            adapters[source_id] = unavailable
        else:
            adapters[source_id] = lambda sid=source_id: ADAPTERS[sid](exchange_rate)

    for router_id, adapter in adapters.items():
        try:
            router_offers = adapter()
            routers.append(
                {
                    **_router_metadata(router_id),
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
                if router_id not in RATE_OPTIONAL_SOURCES:
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
