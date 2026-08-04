#!/usr/bin/env python3
"""
Self-check for slice 04 (provider drill-down + sovereignty badges).

The expand/collapse is client JS (no JS runner here), so this pins the Python ->
JS data contract the drill-down and badges depend on:

  1. Each rendered model carries a `providers` array; each provider row has the
     fields the drill-down renders (name, input/cached/output, quantization,
     context_size, features) plus audio_cost/speech_cost only when the source
     published them.
  2. The baked PROVIDERS table is present and matches the known sovereignty/ZDR
     sets from plan.md ("Sovereignty & ZDR"): 15 total, 10 EU-native, ZDR = all
     except azure_sc and azure_spc.
  3. Badges come from the table, so a non-ZDR provider (azure_sc) must not carry
     the ZDR flag and an EU-native provider (nebius) must carry the EU flag.

Run:  python3 test_cortecs_drilldown.py
Expects docs/cortecs.html already generated (python generate_html.py --no-fetch).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
HTML = ROOT / "docs" / "cortecs.html"
DATA = ROOT / "cortecs.json"

REQUIRED_ROW = ("name", "input", "cached", "output", "quantization", "context_size", "features")

# Known sets the derived table must match (plan.md "Sovereignty & ZDR").
KNOWN_ALL = {
    "aki", "amazon_ireland", "amazon_paris", "azure_sc", "azure_spc", "berget",
    "google", "inceptron", "infercom", "ionos", "mistral", "nebius", "ovh",
    "scaleway", "tensorix",
}
KNOWN_EU = {
    "aki", "berget", "inceptron", "infercom", "ionos", "mistral", "nebius",
    "ovh", "scaleway", "tensorix",
}
KNOWN_ZDR = KNOWN_ALL - {"azure_sc", "azure_spc"}


def extract(html: str, const: str) -> str:
    # ALL_MODELS is `[...];`, PROVIDERS is `{...};`. No top-level `];`/`};` occurs
    # inside either (nested arrays/objects end with `,`), so non-greedy to the
    # first matching close is the full value.
    close = "]" if const == "ALL_MODELS" else "}"
    m = re.search(rf"const {const}\s*=\s*(.+?){re.escape(close)};", html, re.DOTALL)
    assert m, f"{const} block not found in rendered cortecs.html"
    return m.group(1) + close


def main():
    assert HTML.exists(), f"missing {HTML} — run: python generate_html.py --no-fetch"
    html = HTML.read_text(encoding="utf-8")
    models = json.loads(extract(html, "ALL_MODELS"))
    providers = json.loads(extract(html, "PROVIDERS"))

    # ── 1. Drill-down rows have the fields the JS renders ─────────────
    assert models, "no models rendered"
    for m in models:
        assert "providers" in m and isinstance(m["providers"], list), \
            f"{m.get('id')}: missing providers array"
        for r in m["providers"]:
            for k in REQUIRED_ROW:
                assert k in r, f"{m['id']}/{r.get('name')}: missing {k}"
            # audio/speech costs ride along only when the source published them
            assert "audio_cost" not in r or isinstance(r["audio_cost"], (int, float))

    # At least one multi-provider model and one audio model exercise the paths.
    multi = [m for m in models if len(m["providers"]) > 1]
    assert multi, "expected at least one multi-provider model for the drill-down"
    audio = [r for m in models for r in m["providers"] if "audio_cost" in r]
    assert audio, "expected at least one provider carrying an audio_cost"

    # Cross-check the audio rows against the source JSON (audio only when present).
    raw_by_id = {m["id"]: m for m in json.loads(DATA.read_text(encoding="utf-8"))["models"]}
    for m in models:
        src = raw_by_id[m["id"]]["providers_details"]
        for r in m["providers"]:
            has_src = "audio_cost" in src[r["name"]].get("pricing", {})
            has_js = "audio_cost" in r
            assert has_src == has_js, f"{m['id']}/{r['name']}: audio_cost presence mismatch"

    # ── 2. The baked table matches the known sovereignty/ZDR sets ──────
    assert set(providers) == KNOWN_ALL, \
        f"provider set mismatch: {sorted(providers)} vs {sorted(KNOWN_ALL)}"
    eu = {p for p, a in providers.items() if a["eu_native"]}
    zdr = {p for p, a in providers.items() if a["zdr"]}
    assert eu == KNOWN_EU, f"EU-native mismatch: {sorted(eu)}"
    assert zdr == KNOWN_ZDR, f"ZDR mismatch: {sorted(zdr)}"

    # ── 3. Badges derive from the table (spot-check the boundary cases) ─
    assert providers["azure_sc"]["zdr"] is False, "azure_sc must NOT be ZDR"
    assert providers["azure_spc"]["zdr"] is False, "azure_spc must NOT be ZDR"
    assert providers["nebius"]["eu_native"] is True, "nebius must be EU-native"

    print(f"OK — {len(models)} models, {len(providers)} providers "
          f"({len(eu)} EU-native, {len(zdr)} ZDR), "
          f"{len(multi)} multi-provider, {len(audio)} audio provider rows.")


if __name__ == "__main__":
    sys.exit(main())
