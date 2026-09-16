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

DEEPSEEK_URL = "https://api-docs.deepseek.com/quick_start/pricing/"  # trailing slash: the bare URL serves a different page
ZAI_PAYGO_URL = "https://docs.z.ai/guides/overview/pricing.md"
ZAI_DEVPACK_URL = "https://docs.z.ai/devpack/overview.md"
# Fallback only — the real value is parsed from the page's CONTEXT LENGTH row.
DEEPSEEK_CONTEXT = 1_048_576

# The devpack overview only prices credits; monthly USD is pinned from plan.md
# (the page itself only confirms "starting at just 18 USD per month"). A tier
# missing here fails loudly — its price genuinely is not on the page.
DEVPACK_MONTHLY_USD = {"Lite": 18, "Pro": 80, "Max": 168}

# Curated preference for which paygo models are visible by default on the
# compare page. If none of these exist upstream anymore, all models become
# visible (and a note is printed) rather than an empty default view.
ZAI_PAYGO_DEFAULT_MODEL_IDS = {"glm-5.1"}

# Curated: the devpack models worth showing (the multiplier table also lists
# vision models like GLM-4.6V). New unlisted rows are skipped with a printed
# note so the curation is visible in CI logs, not silent.
DEV_PACK_MODEL_IDS = {"glm-5.3", "glm-5.3-flash"}

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


def parse_context_len(cell: str) -> int:
    """'1M' -> 1048576, '128K' -> 131072, '1,048,576' -> 1048576."""
    m = re.match(r"([\d,.]+)\s*([KM]?)", cell.strip().upper())
    assert m, f"unparseable context length: {cell!r}"
    return int(float(m.group(1).replace(",", ""))
               * {"": 1, "K": 1024, "M": 1024 ** 2}[m.group(2)])

def parse_deepseek_table(table_html: str, page_text: str) -> dict:
    """DeepSeek pricing table -> paygo provider entry. Layout-tolerant:

    - models are whatever the MODEL row lists (footnote markers stripped)
    - prices are the cells after each OFF-PEAK/PEAK marker cell
    - the off-peak discount and hours come from the footnote text
    New/retired models and price changes flow through; only a missing price
    row or a column-count mismatch fails loudly.
    """
    rows = html_table_rows(table_html)

    model_row = next((r for r in rows if r and r[0] == "MODEL"), None)
    assert model_row and len(model_row) > 1, "no MODEL row on DeepSeek pricing page"
    model_ids = [re.sub(r"\(\d+\)$", "", c).strip() for c in model_row[1:]]

    ctx_row = next((r for r in rows if r and r[0].startswith("CONTEXT LENGTH")), None)
    if ctx_row and len(ctx_row) > 1:
        vals = [parse_context_len(c) for c in ctx_row[1:]]
        contexts = vals + [vals[-1]] * (len(model_ids) - len(vals))  # colspan = shared
    else:
        contexts = [DEEPSEEK_CONTEXT] * len(model_ids)

    prices, metric = {}, None
    for r in rows:
        band_i = next((i for i, c in enumerate(r) if c in ("OFF-PEAK", "PEAK")), None)
        if band_i is None:
            continue
        band = "off_peak" if r[band_i] == "OFF-PEAK" else "peak"
        vals = [parse_price(c) for c in r[band_i + 1:]]
        label = next((c for c in r if c.startswith("1M ")), None)
        if label is not None:
            metric = re.sub(r"\s*\(", " (", label)
        assert metric, f"price row before any 1M-metric label: {r}"
        assert len(vals) == len(model_ids), \
            f"{metric} ({band}): {len(vals)} prices for {len(model_ids)} models"
        prices.setdefault(metric, {})[band] = vals

    def metric_for(sub: str) -> dict:
        found = [v for k, v in prices.items() if sub in k]
        assert len(found) == 1 and "peak" in found[0] and "off_peak" in found[0], \
            f"need exactly one {sub!r} pricing row with both bands: {prices}"
        return found[0]

    hit, miss, out = (metric_for("CACHE HIT"), metric_for("CACHE MISS"),
                      metric_for("OUTPUT"))

    models = [
        {
            "id": mid,
            "input": miss["peak"][i],
            "input_cache": hit["peak"][i],
            "output": out["peak"][i],
            "off_peak_input": miss["off_peak"][i],
            "off_peak_input_cache": hit["off_peak"][i],
            "off_peak_output": out["off_peak"][i],
            "context": contexts[i],
            "default_visible": not mid.endswith("-exp"),
        }
        for i, mid in enumerate(model_ids)
    ]
    for m in models:  # off-peak is a discount; if this flips, the bands got mixed up
        assert all(m[k] <= m[k.replace("off_peak_", "")] for k in
                   ("off_peak_input", "off_peak_input_cache", "off_peak_output")), m

    disc = re.search(r"off-peak rates are (?:half|(\d+)%)", page_text, re.I)
    assert disc, "no off-peak discount sentence on DeepSeek pricing page"
    off_peak_multiplier = 0.5 if not disc.group(1) else int(disc.group(1)) / 100

    seg = re.search(r"peak hours are ([^.]+)", page_text, re.I)
    assert seg, "no peak-hours sentence on DeepSeek pricing page"
    spans = re.findall(r"(\d{1,2}:\d{2})\s*[-\u2013]\s*(\d{1,2}:\d{2})", seg.group(1))
    assert spans, f"no time spans in peak-hours text: {seg.group(1)!r}"
    off_peak_label = "Outside " + (
        "Mon\u2013Fri " if re.search(r"monday", seg.group(1), re.I) else ""
    ) + " and ".join(f"{a}\u2013{b}" for a, b in spans) + " UTC"

    return {"id": "deepseek", "name": "DeepSeek", "pricing_type": "paygo",
            "currency": "USD", "off_peak_multiplier": off_peak_multiplier,
            "off_peak_label": off_peak_label, "models": models}

def scrape_deepseek() -> dict:
    html = fetch_text(DEEPSEEK_URL)
    table = re.search(r"<table.*?</table>", html, re.S)
    assert table, "no <table> found on DeepSeek pricing page"
    page_text = re.sub(r"<[^>]+>", " ", html_mod.unescape(html))
    return parse_deepseek_table(table.group(0), page_text)


def parse_zai_paygo(md: str) -> dict:
    """Text-models markdown table -> paygo provider entry. Roster-generic:
    models and prices are whatever the table lists; only the header shape
    (Model / Input / Cached Input / Output) is a hard requirement.
    """
    section = md.split("### Text Models", 1)
    assert len(section) == 2, "no '### Text Models' section on z.ai pricing page"
    table = next(
        (t for t in parse_markdown_tables(section[1])
         if t and {"Model", "Input", "Cached Input", "Output"} <= set(t[0])),
        None,
    )
    assert table, "no table with Model/Input/Cached Input/Output headers in Text Models"
    header, *rows = table
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
    assert models, "no text models parsed from z.ai pricing page"
    assert len({m["id"] for m in models}) == len(models), \
        f"duplicate model ids: {sorted(m['id'] for m in models)}"
    if not any(m["default_visible"] for m in models):
        print(f"Note: none of the preferred z.ai paygo models "
              f"{sorted(ZAI_PAYGO_DEFAULT_MODEL_IDS)} exist anymore — "
              f"showing all {len(models)} models by default")
        for m in models:
            m["default_visible"] = True
    return {"id": "zai", "name": "z.ai", "pricing_type": "paygo",
            "currency": "USD", "models": models}


def scrape_zai_paygo() -> dict:
    return parse_zai_paygo(fetch_text(ZAI_PAYGO_URL))


def parse_zai_devpack(md: str) -> dict:
    """Devpack overview: tiers, credit multipliers, off-peak -> subscription entry.

    Tier names, weekly credits, multipliers and the off-peak schedule come from
    the page. Monthly USD stays pinned (not priced anywhere on the page) — a
    new tier fails loudly asking for its price.
    """
    tiers_table = next(
        t for t in parse_markdown_tables(md)
        if t and t[0] and "Weekly Credits" in t[0]
    )
    header = tiers_table[0]
    name_i = header.index("Plan Type")
    weekly_i = header.index("Weekly Credits")
    tiers = []
    for row in tiers_table[1:]:
        name = row[name_i]
        assert name in DEVPACK_MONTHLY_USD, \
            f"new devpack tier {name!r}: add its monthly USD to DEVPACK_MONTHLY_USD"
        tiers.append({
            "name": name,
            "monthly_usd": DEVPACK_MONTHLY_USD[name],
            "weekly_credits": int(row[weekly_i].replace(",", "")),
        })
    assert tiers, "no devpack tiers parsed"
    assert len({t["name"] for t in tiers}) == len(tiers), tiers

    html_table = re.search(r"<table>.*?</table>", md, re.S)
    assert html_table, "no multiplier <table> on devpack page"
    models = []
    for cells in html_table_rows(html_table.group(0)):
        if len(cells) < 4 or not cells[-4].startswith("GLM-"):
            continue
        mid = re.split(r"\\|\n|\s+\(", cells[-4], maxsplit=1)[0].lower()
        if mid not in DEV_PACK_MODEL_IDS:
            print(f"Note: skipping devpack table row {mid!r} — not in curated "
                  f"DEV_PACK_MODEL_IDS; add it there if it is a devpack-"
                  f"supported coding model")
            continue
        models.append(
            {
                "id": mid,
                "mult_input": float(cells[-3]),
                "mult_cached": float(cells[-2]),
                "mult_output": float(cells[-1]),
                "default_visible": True,
            }
        )
    assert models, f"no curated models ({sorted(DEV_PACK_MODEL_IDS)}) in devpack table"
    assert all(m["mult_input"] > 0 and m["mult_output"] > 0 for m in models), models

    pct = re.search(r"off-peak hours[^.]*?(\d+)%", md, re.I)
    assert pct, "no off-peak percentage on devpack page"
    off_peak_multiplier = float(pct.group(1)) / 100
    assert 0 < off_peak_multiplier <= 1, off_peak_multiplier

    peak = re.search(r"\*\*Peak hours\*\*[:\s]*([^\n]+)", md)
    assert peak, "no peak-hours label on devpack page"
    off_peak_label = normalize_peak_label(peak.group(1).strip().rstrip("."))

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


def scrape_zai_devpack() -> dict:
    return parse_zai_devpack(fetch_text(ZAI_DEVPACK_URL))


def self_check(providers: list[dict], prev: list[dict] | None = None) -> None:
    """Structural invariants + a change notice vs the previous providers.json.

    No pinned rosters or prices: model/pricing changes upstream flow through and
    are only printed here so a human still sees them in CI logs.
    """
    assert [p["id"] for p in providers] == ["deepseek", "zai", "zai-devpack"], providers
    assert [p["pricing_type"] for p in providers] == ["paygo", "paygo", "subscription"]
    if not prev:
        return
    old = {p["id"]: p for p in prev}
    for p in providers:
        o = old.get(p["id"])
        if o is None:
            print(f"Note: provider {p['id']!r} added")
            continue
        if o == p:
            continue
        def ids(x):
            return {m.get("id") or m.get("name") for m in x.get("models", x.get("tiers", []))}
        print(f"Note: provider {p['id']} changed vs previous providers.json: "
              f"+{sorted(ids(p) - ids(o))} -{sorted(ids(o) - ids(p))}")

def build() -> dict:
    """Three scrapers + self-check -> the providers.json payload."""
    providers = [scrape_deepseek(), scrape_zai_paygo(), scrape_zai_devpack()]
    prev_path = Path(__file__).parent / "providers.json"
    prev = None
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8")).get("providers")
        except (ValueError, OSError):
            pass  # unreadable previous file -> skip the change notice
    self_check(providers, prev)
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
    # parse_deepseek_table against a trimmed copy of the live table (2026 layout:
    # rowspan labels, footnote markers, OFF-PEAK row before PEAK).
    got = parse_deepseek_table(
        '<table><tr><td colspan="3">MODEL</td><td>deepseek-flash<sup>(1)</sup></td>'
        '<td>deepseek-v4-pro<sup>(2)</sup></td></tr>'
        '<tr><td colspan="3">CONTEXT LENGTH</td><td colspan="2">1M</td></tr>'
        '<tr><td rowspan="2">PRICING</td><td rowspan="2">1M INPUT TOKENS<br>(CACHE HIT)</td>'
        '<td>OFF-PEAK</td><td>$0.003</td><td>$0.022</td></tr>'
        '<tr><td>PEAK</td><td>$0.006</td><td>$0.044</td></tr>'
        '<tr><td rowspan="2">1M INPUT TOKENS<br>(CACHE MISS)</td>'
        '<td>OFF-PEAK</td><td>$0.15</td><td>$0.66</td></tr>'
        '<tr><td>PEAK</td><td>$0.3</td><td>$1.32</td></tr>'
        '<tr><td rowspan="2">1M OUTPUT TOKENS</td>'
        '<td>OFF-PEAK</td><td>$0.6</td><td>$1.98</td></tr>'
        '<tr><td>PEAK</td><td>$1.2</td><td>$3.96</td></tr></table>',
        "Off-peak rates are half of the peak rates. Peak hours are "
        "01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday.",
    )
    flash, pro = got["models"]
    assert flash == {"id": "deepseek-flash", "input": 0.3, "input_cache": 0.006,
                     "output": 1.2, "off_peak_input": 0.15, "off_peak_input_cache": 0.003,
                     "off_peak_output": 0.6, "context": 1_048_576, "default_visible": True}, flash
    assert pro["id"] == "deepseek-v4-pro" and pro["output"] == 3.96
    assert got["off_peak_multiplier"] == 0.5
    assert got["off_peak_label"] == "Outside Mon–Fri 01:00–04:00 and 06:00–10:00 UTC", got["off_peak_label"]
    # z.ai paygo: roster-generic parse + default-visibility preference.
    zai_md = (
        "### Text Models\n"
        "| Model | Input | Cached Input | Output |\n"
        "|---|---|---|---|\n"
        "| GLM-5.1 | $1.4 / MTok | $0.26 / MTok | $4.4 / MTok |\n"
        "| GLM-4.6 | $0.6 / MTok | $0.14 / MTok | $2.2 / MTok |\n"
    )
    zai = parse_zai_paygo(zai_md)
    assert [m["id"] for m in zai["models"]] == ["glm-5.1", "glm-4.6"]
    assert zai["models"][0]["default_visible"] and not zai["models"][1]["default_visible"]
    zai2 = parse_zai_paygo(zai_md.replace("GLM-5.1", "GLM-9"))  # prints note
    assert all(m["default_visible"] for m in zai2["models"]), zai2["models"]
    # z.ai devpack: tiers + multipliers + off-peak from the page; USD stays pinned.
    devpack_md = (
        "| Plan Type | Weekly Credits |\n|---|---|\n| Lite | 10,000 |\n| Pro | 60,000 |\n\n"
        "<table>"
        "<tr><td>GLM-5.3</td><td>6.9</td><td>1.7</td><td>24</td></tr>"
        "<tr><td>GLM-4.6V (vision)</td><td>1</td><td>1</td><td>1</td></tr>"
        "</table>\n\n"
        "During off-peak hours, enjoy 50% off. "
        "**Peak hours**: Monday to Friday, 14:00–18:00 Singapore Standard Time (UTC+8).\n"
    )
    dp = parse_zai_devpack(devpack_md)
    assert dp["tiers"] == [{"name": "Lite", "monthly_usd": 18, "weekly_credits": 10000},
                            {"name": "Pro", "monthly_usd": 80, "weekly_credits": 60000}]
    assert [m["id"] for m in dp["models"]] == ["glm-5.3"]  # GLM-4.6V skipped w/ note
    assert dp["models"][0]["mult_output"] == 24
    assert dp["off_peak_multiplier"] == 0.5
    assert dp["off_peak_label"] == "Mon–Fri 14:00–18:00 UTC+8", dp["off_peak_label"]
    try:  # a tier with no pinned monthly USD must fail loudly
        parse_zai_devpack(devpack_md.replace("| Lite |", "| Free |"))
        raise SystemExit("self-check failed: unpinned tier accepted")
    except AssertionError:
        pass
    main()
