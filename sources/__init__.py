"""Source registry for the shared fetch layer.

Each entry describes one pricing source and declares which page(s) it feeds
via `pages`; each page's build step selects its sources from this field.
Every source feeds the global Model Price Calculator page. The gateway
catalogs publish no EU routing and therefore feed only the global page; the
routers and first-party APIs also feed the EU router page.

`sellerKind` classifies the source as a Seller for the global page (router,
gateway, or first-party API). `kind` stays the EU page's direct-baseline
marker and is unchanged.
"""

from fetch_providers import DEEPSEEK_URL, ZAI_PAYGO_URL
from sources.aiand import AIAND_URL
from sources.aimlapi import AIMLAPI_URL
from sources.claude_direct import CLAUDE_MODELS_URL, CLAUDE_PRICING_URL
from sources.chutes import CHUTES_URL
from sources.cortecs import CORTECS_URL
from sources.deepinfra import DEEPINFRA_URL
from sources.eurouter import EUROUTER_URL
from sources.kilo import KILO_URL
from sources.llm_gateway import LLM_GATEWAY_URL
from sources.nano_gpt import NANO_GPT_URL
from sources.novita import NOVITA_URL
from sources.openai_direct import OPENAI_MODELS_URL, OPENAI_PRICING_URL
from sources.opencode import OPENCODE_ZEN_URL
from sources.openrouter import OPENROUTER_URL
from sources.requesty import REQUESTY_URL
from sources.vercel_gateway import VERCEL_GATEWAY_URL

SOURCES = {
    "cortecs": {
        "name": "Cortecs",
        "pages": ("router", "global"),
        "sellerKind": "router",
        "source": CORTECS_URL,
        "euClaim": "EU catalog: providers based and regulated within the EU.",
    },
    "eurouter": {
        "name": "EUrouter",
        "pages": ("router", "global"),
        "sellerKind": "router",
        "source": EUROUTER_URL,
        "euClaim": "EU handling is EUrouter's baseline routing guarantee.",
    },
    "openrouter": {
        "name": "OpenRouter",
        "pages": ("router", "global"),
        "sellerKind": "router",
        "source": OPENROUTER_URL,
        "euClaim": "EU regional routing; Business or Enterprise plan required.",
    },
    "opencode": {
        "name": "OpenCode Zen",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": OPENCODE_ZEN_URL,
        "euClaim": "No EU routing catalog is published.",
    },
    "deepinfra": {
        "name": "DeepInfra",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": DEEPINFRA_URL,
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "novita": {
        "name": "Novita",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": NOVITA_URL,
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "requesty": {
        "name": "Requesty",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": REQUESTY_URL,
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "vercel-gateway": {
        "name": "Vercel AI Gateway",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": VERCEL_GATEWAY_URL,
        # Vercel AI Gateway charges the provider's list price with zero
        # markup and bills it in US dollars (vercel.com/docs/ai-gateway/
        # pricing: "You pay the provider's list price").
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "kilo": {
        "name": "Kilo",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": KILO_URL,
        # Kilo bills the gateway per token in US dollars with "microdollar
        # precision (1 USD = 1,000,000 microdollars)" (kilo.ai/docs/gateway/
        # usage-and-billing), and the catalog's per-token decimals match the
        # providers' USD list prices.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "nano-gpt": {
        "name": "nano-gpt",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": NANO_GPT_URL,
        # nano-gpt's pricing page bills text API usage "at the model's list
        # price" in USD; every catalog row prices currency USD.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "chutes": {
        "name": "Chutes",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": CHUTES_URL,
        # Chutes calls itself "a decentralized, serverless inference
        # platform for open-source AI models" (chutes.ai). Its pricing page
        # quotes the catalog rows in dollars per 1M tokens ("Costs are
        # charged per million tokens, separately for input and output"),
        # with TAO only an alternative payment method, and the catalog's
        # price fields name the currency usd (chutes.ai/pricing).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "llmgateway": {
        "name": "LLM Gateway",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": LLM_GATEWAY_URL,
        # LLM Gateway's model directory renders the catalog's per-token
        # decimals as dollars per 1M tokens ("Input $0.15 /M tokens Cache
        # Read $0.075 /M tokens Output $0.6 /M tokens" for gpt-4o-mini,
        # llmgateway.io/models/gpt-4o-mini), and the pricing page bills
        # add-ons like data retention at $0.01 per 1M tokens.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "aiand": {
        "name": "aiand",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": AIAND_URL,
        # ai& "serves open-weight LLMs from our own infrastructure ... with
        # per-token credit billing" (docs.aiand.com) — a hosted inference
        # platform, not a router. The keyless catalog bills US dollars:
        # every row prices currency "usd" and "Called without an API key,
        # the endpoint returns USD prices" (docs.aiand.com/models/pricing).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "aimlapi": {
        "name": "AI/ML API",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": AIMLAPI_URL,
        # AI/ML API self-describes as "One API for 1000+ AI models ... under
        # one bill" (aimlapi.com) — a gateway, not a router. Its Complete
        # Model List doc ends the price walkthrough with "Prices are in USD
        # and are what you are charged" (docs.aimlapi.com/
        # api-references/service-endpoints/complete-model-list.md), and the
        # account balance API documents its currency as "balance currency
        # (always USD)".
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "deepseek-direct": {
        "name": "DeepSeek API",
        "pages": ("router", "global"),
        "source": DEEPSEEK_URL,
        "kind": "direct",
        "sellerKind": "first-party",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "zai-direct": {
        "name": "z.ai API",
        "pages": ("router", "global"),
        "source": ZAI_PAYGO_URL,
        "kind": "direct",
        "sellerKind": "first-party",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "claude-direct": {
        "name": "Claude API",
        "pages": ("router", "global"),
        "source": CLAUDE_PRICING_URL,
        "catalogSource": CLAUDE_MODELS_URL,
        "kind": "direct",
        "sellerKind": "first-party",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "openai-direct": {
        "name": "OpenAI API",
        "pages": ("router", "global"),
        "source": OPENAI_PRICING_URL,
        "catalogSource": OPENAI_MODELS_URL,
        "kind": "direct",
        "sellerKind": "first-party",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
}
