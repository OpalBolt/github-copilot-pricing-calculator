#!/usr/bin/env python3
"""Usage-ranked default view for the Model Price Calculator.

Ranks OpenRouter usage rows ({date, model_permaslug, total_tokens}) into
the most-used models — at most a few per creator — and matches them to
Seller listings by normalized slug equality. The page opens on the matched
listings; the full catalog stays reachable through search.

The selection is pure: select_default_view is fed a rankings payload and
listings and never fetches. The fetching seam is the chain in
resolve_default_view: it fetches OpenRouter's rankings-daily dataset live
behind the build's only secret (OPENROUTER_DATASETS_KEY), falls back to the
previous build's stored selection for at most seven days, then to the
committed fixture snapshot, and finally to no selection at all. A failed or
keyless fetch never fails the build (ADR 0005); tests patch the seam
functions.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "openrouter-rankings.json"
# OpenRouter's rankings-daily dataset (docs: Data API cookbook). The default
# 30-day window needs no query parameters; a missing or invalid key gets 401.
RANKINGS_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
LIVE_RANKINGS_SOURCE = "openrouter-rankings-daily"
# The previous build's selection stays usable for this long (ADR 0005).
SELECTION_MAX_AGE = timedelta(days=7)

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
    """The committed fixture snapshot — the chain's last usable rankings
    payload. Never raises: a failed read returns None and the page loads
    search-only rather than failing the build."""
    try:
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch_live_rankings(key: str) -> dict | None:
    """One keyed GET of the rankings-daily dataset: the same 30-day
    {date, model_permaslug, total_tokens} rows the committed snapshot holds.
    Returns None when the endpoint fails or answers with an unusable
    payload; no exception escapes, so a failing endpoint never fails the
    build. The key value is read from the environment at fetch time only —
    it is never committed, logged, or embedded."""
    request = urllib.request.Request(
        RANKINGS_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "github-copilot-pricing-calculator/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        # Anything the request, body read, or JSON parse can raise — socket
        # timeouts, truncated transfers (http.client.IncompleteRead),
        # undecodable or malformed bodies — degrades to the chain; no
        # exception escapes, so a failing endpoint never fails the build.
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    return payload


def load_live_rankings() -> dict | None:
    """The live rankings payload when OPENROUTER_DATASETS_KEY is set and the
    endpoint answers; None otherwise. An absent key is not an error and
    makes no request."""
    key = os.environ.get("OPENROUTER_DATASETS_KEY", "").strip()
    if not key:
        return None
    return fetch_live_rankings(key)


def _stored_selection(previous: dict | None) -> dict | None:
    """The previous build's stored selection, reused verbatim while its
    fetchedAt is younger than SELECTION_MAX_AGE. Missing, malformed, or
    expired selections are unusable so the chain falls through."""
    view = (previous or {}).get("defaultView")
    if not (
        isinstance(view, dict)
        and view.get("models")
        and view.get("listingKeys")
        and view.get("fetchedAt")
    ):
        return None
    try:
        fetched = datetime.fromisoformat(str(view["fetchedAt"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    # An offset-naive timestamp has no absolute age: treat it as malformed
    # so the age subtraction below cannot raise.
    if fetched.tzinfo is None:
        return None
    if now_utc() - fetched > SELECTION_MAX_AGE:
        return None
    return view


def _snapshot_source(payload: dict) -> str:
    """The committed snapshot's name: the rankings source plus the date the
    snapshot was taken, so the dataset names exactly the data it opened on."""
    meta = payload.get("meta") or {}
    stamp = str(meta.get("as_of") or meta.get("end_date") or "unknown")[:10]
    return f"openrouter-rankings-snapshot-{stamp}"


def resolve_default_view(previous: dict | None, listings: list[dict]) -> dict | None:
    """The page's opening selection from the first usable rankings source:
    the live keyed fetch, then the previous build's stored selection
    (stale-marked, seven-day expiry), then the committed fixture snapshot
    (stale-marked, no expiry — refreshing it is a maintainer action), then
    None so the page loads search-only. Each step is pure selection math on
    top of the source; no failure here raises."""
    live = load_live_rankings()
    if live:
        selection = select_default_view(live, listings)
        if selection:
            selection["source"] = LIVE_RANKINGS_SOURCE
            return selection
    stored = _stored_selection(previous)
    if stored:
        return {**stored, "stale": True}
    fixture = load_rankings()
    if fixture:
        selection = select_default_view(fixture, listings)
        if selection:
            selection["source"] = _snapshot_source(fixture)
            selection["stale"] = True
            return selection
    return None
