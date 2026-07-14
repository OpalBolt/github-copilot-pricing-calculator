#!/usr/bin/env python3
"""
fetch_pricing.py

Scrapes the GitHub Copilot models-and-pricing page and outputs a JSON
summary of all models with their rates per 1M tokens.

Usage:
    python fetch_pricing.py              # fetch + write pricing.json

This module's functions (fetch_markdown, parse_tables) are importable by
generate_html.py for orchestration.

Requires: Python 3.8+ (stdlib only — urllib, re, json)
"""

import argparse
import json
import re
import urllib.request
from datetime import date
from pathlib import Path

API_URL = (
    "https://docs.github.com/api/article/body"
    "?pathname=/en/copilot/reference/copilot-billing/models-and-pricing"
)

PRICE_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)")
PROVIDER_RE = re.compile(r"^###\s+(.+)")
# A separator row contains only |, -, :, and spaces (e.g. "| --- | -----: | ---: |")
SEPARATOR_RE = re.compile(r"^\|[-|: ]+\|$")
# Footnote reference: [^name]
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
# Footnote definition: [^name]: text
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s+(.+)$")


def fetch_markdown(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-pricing/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def is_separator(line: str) -> bool:
    return bool(SEPARATOR_RE.match(line)) and "-" in line


def parse_tables(markdown: str) -> tuple[list[dict], dict[str, str]]:
    """
    Parse pricing tables and footnotes from markdown.
    
    Returns:
        (models, footnotes) where footnotes is a dict mapping footnote_id -> text
    """
    models = []
    footnotes = {}
    provider = "Unknown"
    headers: list[str] = []

    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect footnote definitions (before table parsing)
        fn_def = FOOTNOTE_DEF_RE.match(line)
        if fn_def:
            footnote_id = fn_def.group(1)
            footnote_text = fn_def.group(2)
            footnotes[footnote_id] = footnote_text
            i += 1
            continue

        # Detect provider section heading (### OpenAI, ### Anthropic, …)
        m = PROVIDER_RE.match(line)
        if m:
            provider = m.group(1).strip()
            headers = []
            i += 1
            continue

        # Skip separator rows
        if is_separator(line):
            i += 1
            continue

        # A table row starts and ends with |
        if not (line.startswith("|") and line.endswith("|")):
            i += 1
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1]  # drop empty strings from leading/trailing |

        # Detect table header row: next non-blank line is a separator
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and is_separator(lines[j].strip()):
            headers = [c for c in cells]
            i = j + 1  # skip past separator
            continue

        # Skip empty-content rows (e.g. blank spacer rows between data rows)
        if not cells or all(c == "" for c in cells):
            i += 1
            continue

        # Data row — only record if we have headers and the first cell is non-empty
        if headers and cells[0] != "":
            obj: dict = {"provider": provider}
            for idx, header in enumerate(headers):
                val = cells[idx].strip() if idx < len(cells) else ""
                # Extract footnote references before stripping them
                footnote_refs = FOOTNOTE_REF_RE.findall(val)
                # Strip footnote markers like [^sonnet-5-promo]
                val = FOOTNOTE_REF_RE.sub("", val).strip()
                pm = PRICE_RE.search(val)
                if pm:
                    obj[header] = float(pm.group(1))
                else:
                    obj[header] = val
                # Store footnote references in the model
                if footnote_refs:
                    obj["_footnotes"] = footnote_refs
            models.append(obj)

        i += 1

    return models, footnotes


def print_summary(models: list[dict]) -> None:
    print("\n── Models found ──────────────────────────────────────────")
    for m in models:
        name = m.get("Model") or m.get("model") or "(unknown)"
        print(f"  [{m['provider']}] {name}")
    print(f"\nTotal: {len(models)} model rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GitHub Copilot model pricing.")
    args = parser.parse_args()

    print("Fetching pricing data from GitHub docs...")
    markdown = fetch_markdown(API_URL)

    models, footnotes = parse_tables(markdown)
    print_summary(models)

    today = date.today().isoformat()
    output = {"fetchDate": today, "models": models}
    if footnotes:
        output["footnotes"] = footnotes
        print(f"Found {len(footnotes)} footnote(s)")

    out_path = Path(__file__).parent / "pricing.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")

    print("\nDone. Run generate_html.py to rebuild index.html with the updated pricing data.")


if __name__ == "__main__":
    main()
