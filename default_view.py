#!/usr/bin/env python3
"""Usage-ranked default view for the Model Price Calculator.

Ranks OpenRouter usage rows ({date, model_permaslug, total_tokens}) into
the most-used models — at most a few per creator — and matches them to
Seller listings by normalized slug equality. The page opens on the matched
listings; the full catalog stays reachable through search.

The selection is pure: select_default_view is fed a rankings payload and
listings and never fetches. load_rankings is the fetching seam — today it
reads the committed fixture snapshot; the live keyed fetch (slice 32)
replaces its body behind the same interface, falling back to the previous
build's stored selection on failure.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "openrouter-rankings.json"

# Ranking knobs: walk the usage ranking top-down keeping at most
# MAX_MODELS_PER_CREATOR models per creator, stopping at MAX_DEFAULT_MODELS.
MAX_MODELS_PER_CREATOR = 3
MAX_DEFAULT_MODELS = 20

_TRAILING_DATE = re.compile(r"\d{8}$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_model_slug(slug: str) -> str:
    """One comparable token for a ranked permaslug or a Seller model id:
    lowercased, creator prefix and trailing `:free` stripped, trailing
    8-digit date stripped, punctuation dropped, so `haiku-4.5`,
    `haiku 4.5`, and `haiku-4-5` compare equal."""
    slug = slug.lower().strip()
    if slug.endswith(":free"):
        slug = slug[: -len(":free")]
    if "/" in slug:
        slug = slug.rsplit("/", 1)[-1]
    return _TRAILING_DATE.sub("", _NON_ALNUM.sub("", slug))


def rank_models(rows: list[dict]) -> list[tuple[str, int]]:
    """`total_tokens` summed per `model_permaslug` over the dataset's
    window, heaviest first, with the `other` bucket dropped."""
    totals: dict[str, int] = {}
    for row in rows:
        slug = str(row.get("model_permaslug", "")).strip()
        if not slug or slug.lower() == "other":
            continue
        try:
            tokens = int(row.get("total_tokens", 0))
        except (TypeError, ValueError):
            continue
        totals[slug] = totals.get(slug, 0) + tokens
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


def select_default_view(rankings: dict | None, listings: list[dict]) -> dict | None:
    """The page's opening selection, or None when no rankings data is
    usable (the page then loads search-only with a visible note).

    Walks the ranking top-down, keeping at most MAX_MODELS_PER_CREATOR per
    creator and stopping at MAX_DEFAULT_MODELS models, then matches each
    ranked model to listings by exact normalized slug equality — never a
    prefix match, so `glm-5.3` never matches `glm-5.3-flash`. A ranked
    model without listings is recorded as a miss; ranked variants that
    normalize the same share one deduplicated set of listing rows. `:free`
    listings are eligible rows — a zero price is a price."""
    if not rankings:
        return None
    rows = rankings.get("data") or []
    ranked = rank_models(rows)
    if not ranked:
        return None

    selected: list[str] = []
    per_creator: dict[str, int] = {}
    for slug, _tokens in ranked:
        if len(selected) >= MAX_DEFAULT_MODELS:
            break
        creator = (slug.rsplit("/", 1)[0] if "/" in slug else slug).lower()
        if per_creator.get(creator, 0) >= MAX_MODELS_PER_CREATOR:
            continue
        per_creator[creator] = per_creator.get(creator, 0) + 1
        selected.append(slug)

    keys_by_slug: dict[str, list[str]] = {}
    for listing in listings:
        key = listing.get("key")
        model_id = listing.get("modelId")
        if key and model_id:
            keys_by_slug.setdefault(normalize_model_slug(str(model_id)), []).append(
                str(key)
            )

    matched_keys: list[str] = []
    misses: list[str] = []
    for slug in selected:
        matched = keys_by_slug.get(normalize_model_slug(slug))
        if matched:
            matched_keys.extend(matched)
        else:
            misses.append(slug)
    listing_keys = list(dict.fromkeys(matched_keys))
    if not listing_keys:
        return None

    meta = rankings.get("meta") or {}
    dates = sorted({str(row["date"]) for row in rows if row.get("date")})
    return {
        "source": "openrouter-rankings",
        "window": {
            "start": meta.get("start_date") or (dates[0] if dates else None),
            "end": meta.get("end_date") or (dates[-1] if dates else None),
        },
        "fetchedAt": meta.get("as_of"),
        "stale": False,
        "models": selected,
        "listingKeys": listing_keys,
        "misses": misses,
    }


def load_rankings() -> dict | None:
    """The rankings payload for this build. Never raises: a failed read
    returns None and the page loads search-only rather than failing the
    build."""
    try:
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
