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
from sources.openai_direct import fetch_openai_direct
from sources.opencode import fetch_opencode
from sources.openrouter import fetch_openrouter
from sources.zai_direct import fetch_zai_direct

ROOT = Path(__file__).parent
OUTPUT_PATH = ROOT / "router-pricing.json"
MAX_STALE_AGE = timedelta(days=7)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _router_metadata(source_id: str) -> dict:
    """One source's registry metadata without the registry-only `pages` field."""
    return {
        key: value
        for key, value in SOURCES[source_id].items()
        if key != "pages"
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

    adapters = {
        "cortecs": fetch_cortecs,
        "eurouter": lambda: fetch_eurouter(exchange_rate),
    }
    if exchange_rate and not ecb_error:
        adapters["openrouter"] = lambda: fetch_openrouter(exchange_rate)
        adapters["opencode"] = lambda: fetch_opencode(exchange_rate)
        adapters["deepseek-direct"] = lambda: fetch_deepseek_direct(exchange_rate)
        adapters["zai-direct"] = lambda: fetch_zai_direct(exchange_rate)
        adapters["claude-direct"] = lambda: fetch_claude_direct(exchange_rate)
        adapters["openai-direct"] = lambda: fetch_openai_direct(exchange_rate)
    elif ecb_error:
        def unavailable_openrouter():
            raise RuntimeError(f"ECB: {ecb_error}")

        adapters["openrouter"] = unavailable_openrouter
        adapters["opencode"] = unavailable_openrouter
        adapters["deepseek-direct"] = unavailable_openrouter
        adapters["zai-direct"] = unavailable_openrouter
        adapters["claude-direct"] = unavailable_openrouter
        adapters["openai-direct"] = unavailable_openrouter

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
                if router_id in {
                    "openrouter",
                    "opencode",
                    "deepseek-direct",
                    "zai-direct",
                    "claude-direct",
                    "openai-direct",
                }:
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
