#!/usr/bin/env python3
"""
fetch_providers.py

Scrapes three provider pricing sources and writes providers.json — the unified
data source for the provider comparison page:

    deepseek     https://api-docs.deepseek.com/quick_start/pricing/  (HTML table)
    zai          https://docs.z.ai/guides/overview/pricing.md        (markdown, text models)
    zai-devpack  https://docs.z.ai/devpack/overview.md               (markdown)

Usage:
    python fetch_providers.py              # fetch + write providers.json

build() is importable by generate_html.py for orchestration. Re-running the
script overwrites providers.json cleanly.

Requires: Python 3.8+ (stdlib only — urllib, re, json, html)
"""

import html as html_mod
import json
import re
import urllib.request
from pathlib import Path

DEEPSEEK_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
ZAI_PAYGO_URL = "https://docs.z.ai/guides/overview/pricing.md"
ZAI_DEVPACK_URL = "https://docs.z.ai/devpack/overview.md"

DEEPSEEK_CONTEXT = 1_048_576  # both models: page says CONTEXT LENGTH 1M

# The devpack overview only prices credits; monthly USD is pinned from plan.md
# (the page itself only confirms "starting at just 18 USD per month").
# ponytail: pinned values; update here + the self-check if z.ai ships new tiers.
DEVPACK_MONTHLY_USD = {"Lite": 18, "Pro": 80, "Max": 168}

# Models the devpack supports. The paygo catalog no longer contains the same
# model IDs, so its latest model is selected separately below.
# ponytail: pinned set; update here if the devpack adds a model.
DEV_PACK_MODEL_IDS = {"glm-5.3", "glm-5.3-flash"}
ZAI_PAYGO_DEFAULT_MODEL_IDS = {"glm-5.1"}

PRICE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-providers/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_price(cell: str) -> float:
    """'$1.4' -> 1.4; 'Free' / '-' / '\\' (not offered) -> 0.0."""
    cell = cell.strip().lower()
    if "free" in cell or cell in {"-", "—", "\\"}:
        return 0.0
    m = PRICE_RE.search(cell)
    assert m, f"unparseable price cell: {cell!r}"
    return float(m.group(1))


def html_table_rows(table_html: str) -> list[list[str]]:
    """Rows of an HTML <table>, cells tag-stripped and unescaped."""
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", table_html, re.S):
        rows.append(
            [
                html_mod.unescape(re.sub(r"<[^>]+>", "", td)).strip()
                for td in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S)
            ]
        )
    return rows


def parse_markdown_tables(text: str) -> list[list[list[str]]]:
    """Every markdown table in text: [headers, *rows] of cell strings."""
    tables, cur = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            cur = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue  # separator row
        if cur is None:
            cur = []
            tables.append(cur)
        cur.append(cells)
    return tables


def normalize_peak_label(label: str) -> str:
    """'Monday to Friday, 14:00–18:00 Singapore Standard Time (UTC+8)' -> 'Mon–Fri 14:00–18:00 UTC+8'."""
    return (
        label.replace("Monday to Friday, ", "Mon–Fri ")
        .replace("Singapore Standard Time ", "")
        .replace("(UTC+8)", "UTC+8")
    )


def scrape_deepseek() -> dict:
    """HTML pricing table -> paygo provider entry."""
    html = fetch_text(DEEPSEEK_URL)
    table = re.search(r"<table.*?</table>", html, re.S)
    assert table, "no <table> found on DeepSeek pricing page"
    rows = html_table_rows(table.group(0))

    model_rows = [r for r in rows if r and r[0] == "MODEL"]
    assert model_rows, "no MODEL row on DeepSeek pricing page"
    model_ids = model_rows[0][1:]
    assert model_ids == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    ], model_rows[0]
    assert any(
        r and r[0] == "CONTEXT LENGTH" and "1M" in r[1] for r in rows
    ), "expected CONTEXT LENGTH = 1M"

    prices = {}
    metric = None
    for r in rows:
        metric_i = next((i for i, cell in enumerate(r) if cell.startswith("1M ")), None)
        if metric_i is not None:
            metric = re.sub(r"\s*\(", " (", r[metric_i])
            assert r[metric_i + 1] == "OFF-PEAK", r
            prices[metric] = {
                "off_peak": [parse_price(c) for c in r[metric_i + 2:]]
            }
        elif metric and r and r[0] == "PEAK":
            prices[metric]["peak"] = [parse_price(c) for c in r[1:]]
            metric = None
    need = {
        "1M INPUT TOKENS (CACHE HIT)",
        "1M INPUT TOKENS (CACHE MISS)",
        "1M OUTPUT TOKENS",
    }
    assert need <= set(prices), f"missing pricing rows: {need - set(prices)}"
    assert all(
        len(band) == len(model_ids)
        for price in prices.values()
        for band in price.values()
    ), prices

    hit = prices["1M INPUT TOKENS (CACHE HIT)"]
    miss = prices["1M INPUT TOKENS (CACHE MISS)"]
    out = prices["1M OUTPUT TOKENS"]

    models = [
        {
            "id": mid,
            "input": miss["peak"][i],
            "input_cache": hit["peak"][i],
            "output": out["peak"][i],
            "off_peak_input": miss["off_peak"][i],
            "off_peak_input_cache": hit["off_peak"][i],
            "off_peak_output": out["off_peak"][i],
            "context": DEEPSEEK_CONTEXT,
            "default_visible": not mid.endswith("-exp"),
        }
        for i, mid in enumerate(model_ids)
    ]
    # ponytail: exact prices pinned from plan.md — fails loudly if the page changes.
    assert models == [
        {"id": "deepseek-v4-flash", "input": 0.44, "input_cache": 0.014,
         "output": 1.32, "off_peak_input": 0.22, "off_peak_input_cache": 0.007,
         "off_peak_output": 0.66, "context": DEEPSEEK_CONTEXT, "default_visible": True},
        {"id": "deepseek-v4-pro", "input": 1.32, "input_cache": 0.044,
         "output": 3.96, "off_peak_input": 0.66, "off_peak_input_cache": 0.022,
         "off_peak_output": 1.98, "context": DEEPSEEK_CONTEXT, "default_visible": True},
        {"id": "deepseek-v4-flash-vision-exp", "input": 0.44, "input_cache": 0.014,
         "output": 1.32, "off_peak_input": 0.22, "off_peak_input_cache": 0.007,
         "off_peak_output": 0.66, "context": DEEPSEEK_CONTEXT, "default_visible": False},
    ], models
    return {"id": "deepseek", "name": "DeepSeek", "pricing_type": "paygo",
            "currency": "USD", "off_peak_multiplier": 0.5,
            "off_peak_label": "Outside Mon–Fri 01:00–04:00 and 06:00–10:00 UTC",
            "models": models}


def scrape_zai_paygo() -> dict:
    """Text-models markdown table -> paygo provider entry."""
    md = fetch_text(ZAI_PAYGO_URL)
    section = md.split("### Text Models", 1)[1].split("### ", 1)[0]
    tables = parse_markdown_tables(section)
    assert len(tables) == 1, f"expected 1 table in Text Models section, got {len(tables)}"
    header, *rows = tables[0]
    for name in ("Model", "Input", "Cached Input", "Output"):
        assert name in header, f"missing header column {name!r}: {header}"
    i_input = header.index("Input")
    i_cached = header.index("Cached Input")
    i_output = header.index("Output")

    models = []
    for row in rows:
        if not row or not row[0]:
            continue
        mid = row[0].lower()
        models.append(
            {
                "id": mid,
                "input": parse_price(row[i_input]),
                "input_cache": parse_price(row[i_cached]),
                "output": parse_price(row[i_output]),
                "default_visible": mid in ZAI_PAYGO_DEFAULT_MODEL_IDS,
            }
        )
    # ponytail: fails loudly if z.ai adds or removes a text model.
    assert len(models) == 12, f"expected 12 text models, got {len(models)}"
    by_id = {m["id"]: m for m in models}
    assert by_id["glm-5.1"] == {"id": "glm-5.1", "input": 1.4, "input_cache": 0.26,
                                "output": 4.4, "default_visible": True}, by_id["glm-5.1"]
    visible = {m["id"] for m in models if m["default_visible"]}
    assert visible == ZAI_PAYGO_DEFAULT_MODEL_IDS, visible
    return {"id": "zai", "name": "z.ai", "pricing_type": "paygo",
            "currency": "USD", "models": models}


def scrape_zai_devpack() -> dict:
    """Devpack overview: tiers, credit multipliers, off-peak -> subscription entry."""
    md = fetch_text(ZAI_DEVPACK_URL)

    tiers_table = next(
        t for t in parse_markdown_tables(md)
        if t and t[0] and "Weekly Credits" in t[0]
    )
    header = tiers_table[0]
    name_i = header.index("Plan Type")
    weekly_i = header.index("Weekly Credits")
    tiers = [
        {
            "name": row[name_i],
            "monthly_usd": DEVPACK_MONTHLY_USD[row[name_i]],
            "weekly_credits": int(row[weekly_i].replace(",", "")),
        }
        for row in tiers_table[1:]
    ]
    assert tiers == [
        {"name": "Lite", "monthly_usd": 18, "weekly_credits": 10000},
        {"name": "Pro", "monthly_usd": 80, "weekly_credits": 60000},
        {"name": "Max", "monthly_usd": 168, "weekly_credits": 140000},
    ], tiers

    html_table = re.search(r"<table>.*?</table>", md, re.S)
    assert html_table, "no multiplier <table> on devpack page"
    models = []
    for cells in html_table_rows(html_table.group(0)):
        if len(cells) < 4 or not cells[-4].startswith("GLM-"):
            continue
        mid = re.split(r"\\|\n|\s+\(", cells[-4], maxsplit=1)[0].lower()
        if mid not in DEV_PACK_MODEL_IDS:
            continue  # GLM-4.6V (vision) — not a devpack-supported coding model
        models.append(
            {
                "id": mid,
                "mult_input": float(cells[-3]),
                "mult_cached": float(cells[-2]),
                "mult_output": float(cells[-1]),
                "default_visible": True,
            }
        )
    assert models == [
        {"id": "glm-5.3", "mult_input": 6.9, "mult_cached": 1.7,
         "mult_output": 24, "default_visible": True},
        {"id": "glm-5.3-flash", "mult_input": 2.3, "mult_cached": 0.56,
         "mult_output": 8, "default_visible": True},
    ], models

    pct = re.search(r"off-peak hours[^.]*?(\d+)%", md, re.I)
    assert pct, "no off-peak percentage on devpack page"
    off_peak_multiplier = float(pct.group(1)) / 100

    peak = re.search(r"\*\*Peak hours\*\*[:\s]*([^\n]+)", md)
    assert peak, "no peak-hours label on devpack page"
    off_peak_label = normalize_peak_label(peak.group(1).strip().rstrip("."))
    assert off_peak_label == "Mon–Fri 14:00–18:00 UTC+8", off_peak_label

    return {
        "id": "zai-devpack",
        "name": "z.ai Devpack",
        "pricing_type": "subscription",
        "currency": "USD",
        "off_peak_multiplier": off_peak_multiplier,
        "off_peak_label": off_peak_label,
        "tiers": tiers,
        "models": models,
    }


def self_check(providers: list[dict]) -> None:
    assert [p["id"] for p in providers] == ["deepseek", "zai", "zai-devpack"], providers
    assert [p["pricing_type"] for p in providers] == ["paygo", "paygo", "subscription"]


def build() -> dict:
    """Three scrapers + self-check -> the providers.json payload."""
    providers = [scrape_deepseek(), scrape_zai_paygo(), scrape_zai_devpack()]
    self_check(providers)
    return {"providers": providers}


def main() -> None:
    print("Fetching provider pricing (deepseek, z.ai paygo, z.ai devpack)...")
    output = build()
    for p in output["providers"]:
        print(f"  {p['id']:<11} {p['pricing_type']:<12} {len(p['models'])} model(s)")
    out_path = Path(__file__).parent / "providers.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    # Offline self-checks of the pure helpers, then fetch + write.
    assert parse_price("$1.4") == 1.4
    assert parse_price("$0.0028") == 0.0028
    assert parse_price("$0.03 / MTok") == 0.03
    assert parse_price("Free") == 0.0
    assert parse_price("-") == 0.0
    assert parse_price("\\") == 0.0
    assert normalize_peak_label(
        "Monday to Friday, 14:00–18:00 Singapore Standard Time (UTC+8)"
    ) == "Mon–Fri 14:00–18:00 UTC+8"
    main()
