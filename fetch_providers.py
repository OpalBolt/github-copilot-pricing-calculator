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

# Models the devpack supports ("All plans support GLM-5.2, GLM-5-Turbo and GLM-4.7").
# z.ai paygo marks exactly these default-visible; the devpack multiplier table
# also lists GLM-4.6V (vision) and MCP servers, which we skip.
# ponytail: pinned set; update here if the devpack adds a model.
DEV_PACK_MODEL_IDS = {"glm-5.2", "glm-5-turbo", "glm-4.7"}

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
    assert model_rows[0][1:] == ["deepseek-v4-flash", "deepseek-v4-pro"], model_rows[0]
    assert any(
        r and r[0] == "CONTEXT LENGTH" and "1M" in r[1] for r in rows
    ), "expected CONTEXT LENGTH = 1M"

    prices = {}
    for r in rows:
        if len(r) >= 3 and r[-3].startswith("1M "):
            prices[r[-3]] = [parse_price(c) for c in r[-2:]]
    need = {
        "1M INPUT TOKENS (CACHE HIT)",
        "1M INPUT TOKENS (CACHE MISS)",
        "1M OUTPUT TOKENS",
    }
    assert need <= set(prices), f"missing pricing rows: {need - set(prices)}"

    hit = prices["1M INPUT TOKENS (CACHE HIT)"]
    miss = prices["1M INPUT TOKENS (CACHE MISS)"]
    out = prices["1M OUTPUT TOKENS"]

    models = [
        {
            "id": mid,
            "input": miss[i],
            "input_cache": hit[i],
            "output": out[i],
            "context": DEEPSEEK_CONTEXT,
            "default_visible": True,
        }
        for i, mid in enumerate(model_rows[0][1:])
    ]
    # ponytail: exact prices pinned from plan.md — fails loudly if the page changes.
    assert models == [
        {"id": "deepseek-v4-flash", "input": 0.14, "input_cache": 0.0028,
         "output": 0.28, "context": DEEPSEEK_CONTEXT, "default_visible": True},
        {"id": "deepseek-v4-pro", "input": 0.435, "input_cache": 0.003625,
         "output": 0.87, "context": DEEPSEEK_CONTEXT, "default_visible": True},
    ], models
    return {"id": "deepseek", "name": "DeepSeek", "pricing_type": "paygo",
            "currency": "USD", "models": models}


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
                "default_visible": mid in DEV_PACK_MODEL_IDS,
            }
        )
    # ponytail: plan.md says 14 text models — fails loudly if z.ai adds/removes one.
    assert len(models) == 14, f"expected 14 text models, got {len(models)}"
    by_id = {m["id"]: m for m in models}
    assert by_id["glm-5.2"] == {"id": "glm-5.2", "input": 1.4, "input_cache": 0.26,
                                "output": 4.4, "default_visible": True}, by_id["glm-5.2"]
    visible = {m["id"] for m in models if m["default_visible"]}
    assert visible == DEV_PACK_MODEL_IDS, visible
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
        mid = cells[-4].lower()
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
        {"id": "glm-5.2", "mult_input": 6.9, "mult_cached": 1.7,
         "mult_output": 24, "default_visible": True},
        {"id": "glm-5-turbo", "mult_input": 5.7, "mult_cached": 1.5,
         "mult_output": 21, "default_visible": True},
        {"id": "glm-4.7", "mult_input": 4.6, "mult_cached": 1.2,
         "mult_output": 16, "default_visible": True},
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
