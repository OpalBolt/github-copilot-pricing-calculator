#!/usr/bin/env python3
"""
Self-check for slice 03 (budget columns).

The cost/runs/free-guard live in client JS (no JS runner here), so this pins the
two things that CAN break silently and that the JS depends on:

  1. The Python -> JS data contract in generate_html.py: each rendered model has
     numeric €/1M rates, cached = cache_read_cost where published else the input
     rate, and free models carry 0s.
  2. The formula itself, as a Python reference: recompute cost + runs from the
     rendered data and assert a paid model yields finite runs while a free model
     yields null (no divide-by-zero) — exactly the JS guard.

Run:  python3 test_cortecs_budget.py
Expects docs/cortecs.html already generated (python generate_html.py --no-fetch).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = ROOT / "docs" / "cortecs.html"
DATA = ROOT / "cortecs.json"


def extract_models(html: str) -> list[dict]:
    m = re.search(r"const ALL_MODELS = (\[.*?\]);", html, re.DOTALL)
    assert m, "ALL_MODELS block not found in rendered cortecs.html"
    return json.loads(m.group(1))


def estimate_cost(m, total=1_000_000, ip=20, cp=60, op=20):
    s = ip + cp + op or 1
    ip, cp, op = ip / s * 100, cp / s * 100, op / s * 100  # normalize like JS
    return (total * ip / 100 / 1_000_000) * m["input"] \
         + (total * cp / 100 / 1_000_000) * m["cached"] \
         + (total * op / 100 / 1_000_000) * (m["output"] or 0)


def main():
    assert HTML.exists(), f"missing {HTML} — run: python generate_html.py --no-fetch"
    models = extract_models(HTML.read_text(encoding="utf-8"))
    raw = json.loads(DATA.read_text(encoding="utf-8"))["models"]
    raw_by_id = {m["id"]: m for m in raw}

    assert len(models) == len(raw), f"row count mismatch: {len(models)} vs {len(raw)}"

    for m in models:
        for k in ("id", "owned_by", "input", "cached", "output"):
            assert k in m, f"{m.get('id')}: missing {k}"
        assert isinstance(m["input"], (int, float)) and m["input"] >= 0
        assert isinstance(m["output"], (int, float)) and m["output"] >= 0
        # cached-fallback contract: cache_read_cost if published, else input rate
        src = raw_by_id[m["id"]]["pricing"]
        crc = src.get("cache_read_cost")
        want = crc if crc is not None else src["input_token"]
        assert m["cached"] == want, f"{m['id']}: cached {m['cached']} != expected {want}"

    # Free-model guard: cost 0 -> runs null (the JS `cost > 0 ? budget/cost : null`).
    free = [m for m in models if estimate_cost(m) == 0]
    assert free, "expected at least one free (€0) model in the dataset"
    for m in free:
        runs = (50 / estimate_cost(m)) if estimate_cost(m) > 0 else None  # mirror JS
        assert runs is None, f"{m['id']}: free model must not produce runs"

    # A paid model must yield finite, positive runs at a €50 budget.
    paid = next(m for m in models if estimate_cost(m) > 0)
    runs = 50 / estimate_cost(paid)
    assert runs > 0 and runs == runs, "paid model runs must be a positive finite number"

    print(f"OK — {len(models)} models, {len(free)} free. "
          f"e.g. {paid['id']}: €{estimate_cost(paid):.4f}/run → {runs:.1f} runs @ €50.")


if __name__ == "__main__":
    sys.exit(main())
