#!/usr/bin/env python3
"""
changelog.py

Diffs the fetched data files on disk against their last committed versions
(git HEAD) and appends human-readable entries to changelog.json — one entry
per category per day:

    copilot    pricing.json        (GitHub Copilot per-model prices)
    providers  providers.json      (deepseek / z.ai / devpack / opencode go)
    router     router-pricing.json (per-router model offers)

Called by generate_html.py after the fetch step and before rendering; the
entries become the Changelog tab on each page. Re-running the same day
replaces that day's entry; an empty diff adds nothing, so days without
data changes are skipped. Requires git + stdlib only.
"""

import json
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
MAX_ENTRIES = 100  # stored per category; pages render the newest ~20
MAX_CHANGES = 50   # lines per day entry before an "… and N more" footer


def head_version(fname: str):
    """A data file's committed JSON at HEAD, or None if unavailable.

    None (no git, file not tracked yet, dirty history) means "no baseline"
    and the category is skipped for the day rather than logging everything
    as newly added.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"HEAD:{fname}"],
            capture_output=True, check=True, timeout=15,
        )
        return json.loads(out.stdout.decode("utf-8"))
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def fmt(v) -> str:
    """0.25 -> '$0.25'; 0 -> 'free'; non-numbers pass through as strings."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    return "free" if v == 0 else f"${v:g}"


def price_deltas(fields: list[tuple[str, object, object]]) -> list[str]:
    """[("input", 1.4, 1.2), ...] -> ["input $1.4→$1.2", ...]; skips None↔None."""
    return [
        f"{label} {fmt(a)}→{fmt(b)}"
        for label, a, b in fields
        if not (a is None and b is None) and a != b
    ]


# ── copilot: pricing.json ────────────────────────────────────────────

def diff_copilot(old: dict, new: dict) -> list[str]:
    fields = ("Input", "Cached input", "Cache write", "Output")
    om = {m["Model"]: m for m in old.get("models", [])}
    nm = {m["Model"]: m for m in new.get("models", [])}
    changes = []
    for name in sorted(om.keys() - nm.keys()):
        changes.append(f"− Removed {name}")
    for name in sorted(nm.keys() - om.keys()):
        m = nm[name]
        changes.append(f"+ Added {name} "
                       f"(in {fmt(m.get('Input'))} · out {fmt(m.get('Output'))})")
    for name in sorted(om.keys() & nm.keys()):
        deltas = price_deltas(
            [(f.lower(), om[name].get(f), nm[name].get(f)) for f in fields]
        )
        if deltas:
            changes.append(f"→ {name}: " + ", ".join(deltas))
    return changes


# ── providers: providers.json ────────────────────────────────────────

PROVIDER_FIELDS = {
    "monthly_usd": "monthly price",
    "off_peak_multiplier": "off-peak multiplier",
    "off_peak_label": "off-peak hours",
}
MODEL_FIELDS = {
    "input": "input",
    "input_cache": "cached",
    "output": "output",
    "mult_input": "credit mult in",
    "mult_cached": "credit mult cached",
    "mult_output": "credit mult out",
    "monthly_limit_usd": "monthly limit",
}


def diff_providers(old: dict, new: dict) -> list[str]:
    op = {p["id"]: p for p in old.get("providers", [])}
    np_ = {p["id"]: p for p in new.get("providers", [])}
    changes = []
    for pid in sorted(op.keys() - np_.keys()):
        changes.append(f"− Provider removed: {op[pid]['name']}")
    for pid in sorted(np_.keys() - op.keys()):
        changes.append(f"+ Provider added: {np_[pid]['name']}")
    for pid in sorted(op.keys() & np_.keys()):
        o, n = op[pid], np_[pid]
        prefix = n["name"]
        deltas = price_deltas(
            [(label, o.get(k), n.get(k)) for k, label in PROVIDER_FIELDS.items()]
        )
        if deltas:
            changes.append(f"→ {prefix}: " + ", ".join(deltas))
        ot = {t["name"]: t for t in o.get("tiers", [])}
        nt = {t["name"]: t for t in n.get("tiers", [])}
        for t in sorted(ot.keys() - nt.keys()):
            changes.append(f"− {prefix}: {t} tier removed")
        for t in sorted(nt.keys() - ot.keys()):
            changes.append(f"+ {prefix}: {t} tier added ({fmt(nt[t]['monthly_usd'])}/mo)")
        for t in sorted(ot.keys() & nt.keys()):
            deltas = price_deltas([
                ("monthly", ot[t].get("monthly_usd"), nt[t].get("monthly_usd")),
                ("weekly credits", ot[t].get("weekly_credits"), nt[t].get("weekly_credits")),
            ])
            if deltas:
                changes.append(f"→ {prefix} {t} tier: " + ", ".join(deltas))
        om = {m["id"]: m for m in o.get("models", [])}
        nm = {m["id"]: m for m in n.get("models", [])}
        for mid in sorted(om.keys() - nm.keys()):
            changes.append(f"− {prefix}: {om[mid].get('name', mid)} removed")
        for mid in sorted(nm.keys() - om.keys()):
            m = nm[mid]
            rates = " (" + " · ".join(
                f"{label} {fmt(m[k])}" for k, label in MODEL_FIELDS.items()
                if m.get(k) is not None and k in ("input", "input_cache", "output",
                                                  "mult_input", "mult_output")
            ) + ")" if m.get("input") or m.get("mult_input") else ""
            changes.append(f"+ {prefix}: {m.get('name', mid)} added{rates}")
        for mid in sorted(om.keys() & nm.keys()):
            deltas = price_deltas(
                [(label, om[mid].get(k), nm[mid].get(k))
                 for k, label in MODEL_FIELDS.items()]
            )
            if deltas:
                changes.append(f"→ {prefix} / {nm[mid].get('name', mid)}: "
                               + ", ".join(deltas))
    return changes


# ── router: router-pricing.json ──────────────────────────────────────

def mode_prices(offer: dict, mode: str) -> dict:
    """A mode's input/cached/output, preferring native-currency prices so
    exchange-rate drift does not register as daily price changes."""
    p = offer.get(mode) or {}
    n = p.get("native") or {}
    return {f: n.get(f, p.get(f)) for f in ("input", "cached", "output")}


def diff_router(old: dict, new: dict) -> list[str]:
    oo = {o["key"]: o for o in old.get("offers", [])}
    no = {o["key"]: o for o in new.get("offers", [])}
    changes = []
    for key in sorted(oo.keys() - no.keys()):
        changes.append(f"− {oo[key]['routerName']}: {oo[key]['name']} removed")
    for key in sorted(no.keys() - oo.keys()):
        changes.append(f"+ {no[key]['routerName']}: {no[key]['name']} added")
    for key in sorted(oo.keys() & no.keys()):
        a, b = oo[key], no[key]
        deltas = []
        for mode in ("default", "eu"):
            pa, pb = mode_prices(a, mode), mode_prices(b, mode)
            deltas += price_deltas([
                (f"{mode} {f}", pa[f], pb[f]) for f in ("input", "cached", "output")
            ])
        if deltas:
            changes.append(f"→ {b['routerName']} / {b['name']}: " + ", ".join(deltas))
    return changes


CATEGORIES = {
    "copilot": ("pricing.json", diff_copilot),
    "providers": ("providers.json", diff_providers),
    "router": ("router-pricing.json", diff_router),
}


def update() -> dict:
    """Diff each data file vs HEAD; write changelog.json; return the log."""
    log_path = ROOT / "changelog.json"
    log = {}
    if log_path.exists():
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass  # unreadable log -> start fresh rather than fail the build
    today = date.today().isoformat()
    for cat, (fname, differ) in CATEGORIES.items():
        path = ROOT / fname
        if not path.exists():
            continue
        old = head_version(fname)
        if old is None:
            continue
        try:
            new = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        changes = differ(old, new)
        if not changes:
            continue
        if len(changes) > MAX_CHANGES:
            changes = changes[:MAX_CHANGES] + [f"… and {len(changes) - MAX_CHANGES} more"]
        entries = [e for e in log.get(cat, []) if e["date"] != today]
        entries.append({"date": today, "changes": changes})
        log[cat] = entries[-MAX_ENTRIES:]
        print(f"changelog: {cat}: {len(changes)} change(s) today")
    log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    return log


if __name__ == "__main__":
    # Offline self-checks of the pure differs.
    cop = diff_copilot(
        {"models": [{"Model": "A", "Input": 1.0, "Cached input": 0.1,
                      "Cache write": "Not applicable", "Output": 2.0},
                    {"Model": "B", "Input": 3.0, "Cached input": 0.3,
                     "Cache write": "Not applicable", "Output": 6.0}]},
        {"models": [{"Model": "A", "Input": 1.25, "Cached input": 0.1,
                      "Cache write": "Not applicable", "Output": 2.0},
                    {"Model": "C", "Input": 0.5, "Cached input": 0.05,
                     "Cache write": "Not applicable", "Output": 1.0}]},
    )
    assert cop == [
        "− Removed B",
        "+ Added C (in $0.5 · out $1)",
        "→ A: input $1→$1.25",
    ], cop

    prv = diff_providers(
        {"providers": [{"id": "zai", "name": "z.ai", "pricing_type": "paygo",
                        "models": [{"id": "glm-5.3", "input": 1.4,
                                    "input_cache": 0.26, "output": 4.4}]}]},
        {"providers": [{"id": "zai", "name": "z.ai", "pricing_type": "paygo",
                        "models": [{"id": "glm-5.3", "input": 1.2,
                                    "input_cache": 0.26, "output": 4.4},
                                   {"id": "glm-5.3-flash", "input": 0.15,
                                    "input_cache": 0.03, "output": 0.5}]}]},
    )
    assert prv == [
        "+ z.ai: glm-5.3-flash added (input $0.15 · cached $0.03 · output $0.5)",
        "→ z.ai / glm-5.3: input $1.4→$1.2",
    ], prv

    rtr = diff_router(
        {"offers": [{"key": "r:a", "routerName": "R", "name": "A",
                     "default": {"input": 1.0, "cached": 0.1, "output": 2.0,
                                 "native": {"input": 1.0, "cached": 0.1, "output": 2.0}}},
                    {"key": "r:b", "routerName": "R", "name": "B",
                     "default": {"input": 5.0, "cached": 0.5, "output": 9.0}}]},
        {"offers": [{"key": "r:a", "routerName": "R", "name": "A",
                     "default": {"input": 1.1, "cached": 0.1, "output": 2.0,
                                 "native": {"input": 1.0, "cached": 0.1, "output": 2.0}}},
                    {"key": "r:b", "routerName": "R", "name": "B",
                     "default": {"input": 5.0, "cached": 0.5, "output": 8.0}}]},
    )
    # r:a native prices unchanged -> USD-only drift is not a change;
    # r:b has no native prices -> its USD drop is one.
    assert rtr == ["→ R / B: default output $9→$8"], rtr

    log = update()
    summary = ", ".join(f"{cat}={len(log.get(cat, []))}" for cat in CATEGORIES)
    print(f"changelog.json: {summary or 'empty'}")
