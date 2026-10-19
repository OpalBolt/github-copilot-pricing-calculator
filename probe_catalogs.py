#!/usr/bin/env python3
"""
probe_catalogs.py

Audits candidate model-catalog endpoints for the live-query aggregator.
Answers three questions per provider, with zero fixing:

  1. Is the endpoint reachable, and is it the right URL?
  2. Does the catalog carry per-model prices (and a declared currency)?
  3. What must happen before the provider is eligible (auth, new URL, a
     second pricing source, ...)?

Verdicts:
  LIVE-PRICED       reachable, catalog parsed, price fields found
  LIVE-NO-PRICES    reachable, catalog parsed, no price fields anywhere
  AUTH-REQUIRED     401/403 — an API key must be sent
  WRONG-URL         404/405 — the path (or host) is wrong
  SERVER-ERROR      5xx — provider-side problem, retry later
  UNREACHABLE       DNS failure, timeout, or connection refused
  NOT-JSON          200 but the body is not a JSON catalog (HTML page / auth wall)
  JSON-NO-CATALOG   200 JSON but no recognizable models array

Usage:
    python3 probe_catalogs.py

Stdlib only. Re-run after fixing a URL or an auth setup to re-verify.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import re
import socket
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 15
MAX_SAMPLE_MODELS = 5
THREADS = 10

# name, url, note (why it is on this list / what to watch for)
PROVIDERS = [
    # --- live sources the site already uses ---
    ("openrouter", "https://openrouter.ai/api/v1/models", "existing source"),
    ("cortecs", "https://api.cortecs.ai/v1/models?extended=true&currency=EUR",
     "existing source; EUR-native — site converts via ECB"),
    ("eurouter", "https://api.eurouter.ai/api/v1/models", "existing source; absent from models.dev"),
    ("zen", "https://opencode.ai/zen/v1/models",
     "WRINKLE CONFIRMED IN CODE: fetch_opencode() joins models.dev api.json "
     "for Zen prices; Zen API entries carry only id/object/created/owned_by. "
     "Decide: scrape their console pricing docs or drop Zen"),

    # --- candidates for the general (non-EU) calculator ---
    ("deepinfra", "https://api.deepinfra.com/v1/models", "confirmed priced"),
    ("novita", "https://api.novita.ai/v3/openai/models", "confirmed priced"),
    ("requesty", "https://router.requesty.ai/v1/models",
     "confirmed priced (799 models)"),
    ("nano-gpt-basic", "https://nano-gpt.com/v1/models",
     "earlier probe: 663 models, no prices"),
    ("nano-gpt", "https://nano-gpt.com/api/v1/models?detailed=true",
     "URL from models.dev sync file — detailed=true may carry prices"),
    ("vercel-gateway", "https://ai-gateway.vercel.sh/v1/models",
     "URL from models.dev sync file (.sh, not .dev)"),
    ("kilo", "https://api.kilo.ai/api/gateway/models",
     "URL from models.dev sync file"),
    ("chutes", "https://llm.chutes.ai/v1/models",
     "URL from models.dev sync file (llm.chutes.ai host)"),
    ("llmgateway", "https://api.llmgateway.io/v1/models",
     "URL from models.dev sync file (.io, not .net)"),

    # --- remaining models.dev sync fleet: verify all, trust none ---
    ("aiand", "https://api.aiand.com/v1/api.json", "from sync file"),
    ("aimlapi", "https://api.aimlapi.com/v1/models?include=pricing,modalities",
     "from sync file"),
    ("ambient", "https://api.ambient.xyz/v1/models", "from sync file"),
    ("anthropic", "https://api.anthropic.com/v1/models",
     "lab; sync runs with a key. Prices live in pricing.md (already scraped "
     "by the site) — this endpoint is not the price source"),
    ("baseten", "https://inference.baseten.co/v1/models", "from sync file"),
    ("crossmodel", "https://www.crossmodel.ai/api/models", "from sync file"),
    ("digitalocean", "https://api.digitalocean.com/v2/gen-ai/models?per_page=200",
     "from sync file"),
    ("edenai", "https://api.edenai.run/v3/models", "from sync file"),
    ("empiriolabs", "https://api.empiriolabs.ai/v1/models", "from sync file"),
    ("engy", "https://api.engy.ai/v1/models", "from sync file"),
    ("friendli", "https://api.friendli.ai/serverless/v1/models", "from sync file"),
    ("github-copilot-yml",
     "https://raw.githubusercontent.com/github/docs/main/data/tables/copilot/"
     "models-and-pricing.yml",
     "YAML, not JSON — NOT-JSON verdict expected. Interesting as a first-party "
     "structured source for the existing Copilot calculator"),
    ("google", "https://generativelanguage.googleapis.com/v1beta/models",
     "lab; pricing is NOT in this API — prices come from their pricing page"),
    ("huggingface", "https://router.huggingface.co/v1/models", "from sync file"),
    ("hyper", "https://hyper.charm.land/v1/models", "from sync file"),
    ("inceptron", "https://api.inceptron.io/v1/models", "from sync file"),
    ("merge-gateway", "https://api-gateway.merge.dev/v1/models", "from sync file"),
    ("meta-docs", "https://dev.meta.ai/docs/pricing-rate-limits.md",
     "markdown pricing doc — NOT-JSON expected, but this IS a first-party "
     "Meta price source (dev.meta.ai). Companion: dev.meta.ai/docs/models.md"),
    ("mistral", "https://api.mistral.ai/v1/models",
     "lab; sync runs with a key"),
    ("nearai", "https://cloud-api.near.ai/v1/models", "from sync file"),
    ("ofox", "https://api.ofox.ai/v2/models/catalog?include=provider_price&limit=500",
     "from sync file"),
    ("ollama-cloud", "https://ollama.com/v1/models", "from sync file"),
    ("openai", "https://api.openai.com/v1/models",
     "lab; sync runs with a key. Prices live in pricing.md (already scraped)"),
    ("pioneer", "https://api.fastino.ai/v1/models", "from sync file"),
    ("prime", "https://api.pinference.ai/api/v1/models", "from sync file"),
    ("tinfoil", "https://inference.tinfoil.sh/v1/models", "from sync file"),
    ("venice", "https://api.venice.ai/api/v1/models?type=text", "from sync file"),
    ("wandb", "https://trace.wandb.ai/inference/modelsdev/models", "from sync file"),
    ("xai", "https://api.x.ai/v1/models",
     "lab; sync runs with a key. Prices live on docs.x.ai pages"),

    # --- endpoints that returned 401 earlier; re-run if a public variant is found ---
    ("together", "https://api.together.xyz/v1/models", "earlier probe: 401"),
    ("groq", "https://api.groq.com/openai/v1/models", "earlier probe: 401"),
    ("fireworks", "https://api.fireworks.ai/inference/v1/models", "earlier probe: 401"),

    # --- sync files with no probeable endpoint ---
    # cloudflare-ai-gateway / cloudflare-workers-ai: URL template needs an
    #   account id + key (api.cloudflare.com/client/v4/accounts/{id}/...) — skip.
    # ovhcloud: sync file exposes no obvious catalog endpoint — needs a manual
    #   look at OVHcloud AI Endpoints docs.
]

PRICE_KEY_RE = re.compile(
    r"price|pricing|cost|per_1m|per_m|input|output|prompt|completion|cache", re.I
)


def _numeric(value) -> bool:
    """True for ints/floats and numeric strings ("0.04", "$1,2")."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        cleaned = value.strip().removeprefix("$").replace(",", "")
        try:
            float(cleaned)
            return cleaned != ""
        except ValueError:
            return False
    return False


def _scan_model(entry: dict):
    """Collect price-ish keys (one nesting level deep) and a declared currency."""
    price_keys, currency = set(), None

    def walk(d):
        nonlocal currency
        for key, value in d.items():
            if key.lower() == "currency" and isinstance(value, str):
                currency = value
            if isinstance(value, dict):
                walk(value)
            elif PRICE_KEY_RE.search(key) and _numeric(value):
                price_keys.add(key)

    walk(entry)
    return price_keys, currency


def _find_models(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("models"), list):
            return result["models"]
    return []


def probe(name: str, url: str) -> dict:
    result = {"name": name, "url": url, "verdict": None, "models": 0,
              "price_keys": set(), "currency": None, "detail": ""}
    request = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "copilot-pricing-probe/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        if status in (401, 403):
            result["verdict"] = "AUTH-REQUIRED"
        elif status in (404, 405):
            result["verdict"] = "WRONG-URL"
        else:
            result["verdict"] = "SERVER-ERROR"
        result["detail"] = f"HTTP {status}"
        return result
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        result["verdict"] = "UNREACHABLE"
        result["detail"] = str(error)[:80]
        return result

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        result["verdict"] = "NOT-JSON"
        result["detail"] = f"HTTP {status}, body starts: {body[:60]!r}"
        return result

    models = _find_models(payload)
    if not models:
        result["verdict"] = "JSON-NO-CATALOG"
        result["detail"] = f"HTTP {status}, top-level keys: {list(payload)[:6]}"
        return result

    for entry in models[:MAX_SAMPLE_MODELS]:
        if isinstance(entry, dict):
            keys, currency = _scan_model(entry)
            result["price_keys"] |= keys
            result["currency"] = result["currency"] or currency

    result["models"] = len(models)
    if result["price_keys"]:
        result["verdict"] = "LIVE-PRICED"
    else:
        result["verdict"] = "LIVE-NO-PRICES"
    return result


ACTIONS = {
    "LIVE-PRICED": "eligible for the aggregator as-is",
    "LIVE-NO-PRICES": "catalog has no prices: find the provider's pricing page/API "
                      "(second source) or exclude the provider",
    "AUTH-REQUIRED": "needs an API key — out of scope for the keyless daily build "
                     "unless the provider documents a public catalog endpoint",
    "WRONG-URL": "URL is wrong: check the provider's docs for their OpenAI-compatible "
                 "models endpoint (common variants: /openai/v1/models, /api/v1/models), "
                 "then fix the URL above and re-run",
    "SERVER-ERROR": "provider-side failure — re-run later before concluding anything",
    "UNREACHABLE": "DNS/network failure or blocking: verify the hostname, then re-run",
    "NOT-JSON": "endpoint returns a page, not a catalog: check for an auth wall or a "
                "docs page URL where a JSON API URL was expected",
    "JSON-NO-CATALOG": "unknown JSON shape: inspect the payload and adjust _find_models",
}


def main() -> None:
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(lambda item: probe(item[0], item[1]), PROVIDERS))

    print(f"{'provider':<16} {'verdict':<16} {'models':>7}  {'currency':<10} url")
    print("-" * 100)
    for item in results:
        currency = item["currency"] or "-"
        print(f"{item['name']:<16} {item['verdict']:<16} {item['models']:>7}  "
              f"{currency:<10} {item['url']}")

    print("\n=== findings and actions ===")
    notes = {name: note for name, _, note in PROVIDERS}
    for item in results:
        if item["verdict"] == "LIVE-PRICED":
            continue
        name = item["name"]
        print(f"\n[{name}] {item['verdict']} ({item['detail'] or 'no extra detail'})")
        print(f"  note: {notes[name]}")
        print(f"  action: {ACTIONS[item['verdict']]}")
        if item["verdict"] == "LIVE-PRICED":
            print(f"  price keys seen: {', '.join(sorted(item['price_keys'])[:8])}")

    priced = [r["name"] for r in results if r["verdict"] == "LIVE-PRICED"]
    print("\n=== summary ===")
    print(f"eligible today ({len(priced)}): {', '.join(priced)}")
    for verdict in ("LIVE-NO-PRICES", "AUTH-REQUIRED", "WRONG-URL",
                    "SERVER-ERROR", "UNREACHABLE", "NOT-JSON", "JSON-NO-CATALOG"):
        names = [r["name"] for r in results if r["verdict"] == verdict]
        if names:
            print(f"{verdict} ({len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    main()
