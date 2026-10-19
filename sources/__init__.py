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
from sources.ambient import AMBIENT_URL
from sources.claude_direct import CLAUDE_MODELS_URL, CLAUDE_PRICING_URL
from sources.chutes import CHUTES_URL
from sources.cortecs import CORTECS_URL
from sources.crossmodel import CROSSMODEL_URL
from sources.deepinfra import DEEPINFRA_URL
from sources.edenai import EDENAI_URL
from sources.empiriolabs import EMPIRIOLABS_URL
from sources.engy import ENGY_URL
from sources.eurouter import EUROUTER_URL
from sources.friendli import FRIENDLI_URL
from sources.hyper import HYPER_URL
from sources.inceptron import INCEPTRON_URL
from sources.kilo import KILO_URL
from sources.llm_gateway import LLM_GATEWAY_URL
from sources.meta import META_PRICING_URL
from sources.mistral import MISTRAL_PRICING_URL
from sources.nano_gpt import NANO_GPT_URL
from sources.nearai import NEARAI_URL
from sources.novita import NOVITA_URL
from sources.ofox import OFOX_URL
from sources.pioneer import PIONEER_URL
from sources.openai_direct import OPENAI_MODELS_URL, OPENAI_PRICING_URL
from sources.opencode import OPENCODE_ZEN_URL
from sources.openrouter import OPENROUTER_URL
from sources.prime import PRIME_URL
from sources.requesty import REQUESTY_URL
from sources.tinfoil import TINFOIL_URL
from sources.venice import VENICE_URL
from sources.vercel_gateway import VERCEL_GATEWAY_URL
from sources.xai import XAI_PRICING_URL

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
    "ambient": {
        "name": "Ambient",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": AMBIENT_URL,
        # Ambient "serves verified AI inference" itself on its open network
        # (ambient.xyz/docs/learn/what-is-ambient) — a hosted inference
        # platform, not a router. Its docs publish the catalog's per-model
        # prices "as USD per million tokens (pricing.input and pricing.
        # output)" (ambient.xyz/docs/build/models).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "crossmodel": {
        "name": "Crossmodel",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": CROSSMODEL_URL,
        # CrossModel self-describes as "a multi-model API gateway — access
        # Claude, GPT, DeepSeek, Gemini and more with one API key"
        # (crossmodel.ai, crossmodel.ai/docs) — a gateway, not a router. It
        # bills a US-dollar wallet: credits are integers "in micro units of
        # currency (1 USD = 1,000,000 micro)" with "Wallet currency, e.g.
        # USD" (crossmodel.ai/docs/api-reference/credits), the site asks
        # users to "Top up in USD", and every catalog row prices currency
        # "USD".
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "edenai": {
        "name": "Eden AI",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": EDENAI_URL,
        # Eden AI self-describes as "One API to Route Best AI Models"
        # (edenai.co) — a multi-provider gateway, not a router. It bills a
        # prepaid credit balance in US dollars: "Every API response
        # includes a cost field showing the charge in USD for that
        # request" and "This is the amount in USD deducted from your
        # balance for that request" (edenai.co/docs/v3/general/
        # buying-credits), and monthly statements cover "one UTC calendar
        # month, in USD" (edenai.co/docs/v3/general/usage-statements).
        "nativeCurrency": "USD",
        "euClaim": "EU data-residency endpoint documented; no EU routing "
        "catalog.",
    },
    "empiriolabs": {
        "name": "Empirio Labs",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": EMPIRIOLABS_URL,
        # Empirio Labs self-describes as "a specialized AI inference and
        # integration provider" that hosts "open-source models on our own
        # GPUs" and runs "optimized endpoints for proprietary models"
        # (empiriolabs.ai) — a hosted inference platform, not a router.
        # Its pricing page states "Prices are listed and billed in USD"
        # (empiriolabs.ai/pricing), and the catalog's pricing_rows render
        # the per-token decimals as dollars per 1M tokens ("$1.40 per 1M
        # prompt tokens" for prompt "0.0000014").
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "engy": {
        "name": "Engy",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": ENGY_URL,
        # Engy self-describes as "OpenAI-compatible inference for frontier
        # open-source LLMs, with a cryptographic proof of correct inference
        # on every response" (engy.ai) and calls itself "the engy gateway"
        # in its docs (engy.ai/docs) — a gateway, not a router. Its pricing
        # page bills "$ per 1M tokens" and states "Prices are live from
        # the billing engine. The API reports the same numbers at https://
        # api.engy.ai/v1/models" (engy.ai/pricing), so the catalog's
        # per-token decimals are US dollars.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "friendli": {
        "name": "FriendliAI",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": FRIENDLI_URL,
        # FriendliAI sells "AI inference services, including serverless
        # APIs, dedicated GPU endpoints, and Bring Your Own GPU (BYOG)"
        # (friendli.ai/pricing) — a hosted inference platform, not a
        # router. It bills in US dollars: "All fees, prices, and other
        # amounts payable under this Agreement are denominated, calculated,
        # and invoiced in U.S. dollars" (friendli.ai/terms-of-service,
        # Payment Process), and its pricing page renders the catalog's
        # per-token decimals as dollars per 1M tokens (rate card unit
        # "1M tokens"; GLM-5.3: inputPrice 1.4 for the catalog's
        # "0.0000014").
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "hyper": {
        "name": "Hyper",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": HYPER_URL,
        # Charm Hyper self-describes as "fast, cost-effective inference
        # built for agentic coding" with one API key and prepaid credits
        # (hyper.charm.land/docs) — a multi-model gateway, not a router.
        # It bills US dollars: its credits doc points at the /v1/models
        # endpoint "for per-model pricing in dollars per million tokens",
        # and the chat-completions usage doc prices each request through
        # "usage.cost.usd — Cost of this request in USD".
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "inceptron": {
        "name": "Inceptron",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": INCEPTRON_URL,
        # Inceptron self-describes as a platform to "run and optimize LLMs
        # on Inceptron's compiler-accelerated platform" with "serverless
        # endpoints" and "elastic GPUs" (inceptron.io) — a hosted inference
        # platform, not a router. It bills in US dollars: its models page
        # quotes every rate card in dollars per 1M tokens ("Input tokens,
        # 1M $1.40 Output tokens, 1M $4.40 Cache read $0.26" for GLM-5.3,
        # inceptron.io/models), and its pricing page pitches commitment
        # discounts as lowering "your effective $/token and $/hr"
        # (inceptron.io/pricing).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "nearai": {
        "name": "NEAR AI",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": NEARAI_URL,
        # NEAR AI Cloud self-describes as "private, verifiable AI inference
        # in Trusted Execution Environments through an OpenAI-compatible
        # API" (docs.near.ai) and routes third-party models "through the
        # NEAR AI Gateway" (docs.near.ai/cloud/models) — a gateway, not a
        # router. It bills US dollars: the pricing API's DecimalPrice doc
        # says the system uses "a fixed scale of 9 (nano-dollars = 1
        # billionth of a dollar)" (docs.near.ai/api-reference/models/
        # list-models-with-pricing), and every DecimalPrice in the public
        # /v1/model/list response carries currency "USD".
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "ofox": {
        "name": "OfoxAI",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": OFOX_URL,
        # OfoxAI self-describes as "One API Key, access to 100+ LLMs"
        # (ofox.ai/docs) — a multi-model gateway, not a router. It bills a
        # US-dollar pay-as-you-go wallet: the balance API documents the
        # account currency as "Currency unit, fixed to \"USD\"" with "All
        # amounts are in USD as 64-bit floats. Internally we track to
        # NanoDollar precision (10⁻⁹ USD)" (ofox.ai/docs/api/openapi/
        # balance), and the catalog's per-token decimals render as dollars
        # per 1M tokens on its own model pages (kimi-k3 "$3 / $15 /M").
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "pioneer": {
        "name": "Pioneer (Fastino)",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": PIONEER_URL,
        # Pioneer (models.dev's name for Fastino's keyless catalog at
        # api.fastino.ai) serves Fastino's own specialized models from its
        # own inference API: "Run specialized inference models or train your
        # own with Fastino's Inference and Training APIs"
        # (docs.fastino.ai/introduction.md) — a hosted inference platform,
        # not a router. Its pricing page bills US dollars: "Token prices
        # are USD per 1M tokens" (docs.fastino.ai/pricing), and the same
        # page's inference table repeats the catalog's per-million fields
        # ($0.08 input / $0.45 output for Nemotron 3.5 Super VL).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "prime": {
        "name": "Prime",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": PRIME_URL,
        # Prime Intellect's inference docs describe "one OpenAI-compatible
        # API for both hosted and gateway models" whose gateway serving
        # "routes the request to an external inference provider" (docs.
        # primeintellect.ai/inference/overview) — a gateway, not a router.
        # It bills US dollars: "Currently, most billing occurs in USD"
        # (docs.primeintellect.ai/faq.md), and every catalog price field
        # names the unit USD per million tokens (input_usd_per_mtok).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "tinfoil": {
        "name": "Tinfoil",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": TINFOIL_URL,
        # Tinfoil self-describes as "a private AI platform" whose inference
        # platform "supports an OpenAI-compatible API for a variety of
        # open-source models" hosted in its own secure enclaves (docs.
        # tinfoil.sh/introduction.md, docs.tinfoil.sh/models/overview.md)
        # — a hosted inference platform, not a router. It bills US dollars:
        # its admin API documents that "Cost fields are reported in
        # nanodollars (1000000000 = $1.00)", key spend caps are "in
        # dollars", and request reconciliation reads "cost_usd" (docs.
        # tinfoil.sh/admin/admin-api.md).
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "venice": {
        "name": "Venice",
        "pages": ("global",),
        "sellerKind": "gateway",
        "source": VENICE_URL,
        # Venice "provides permissionless access to AI models" through one
        # OpenAI-compatible API, serving third-party models anonymized or
        # in TEE/E2EE enclaves (docs.venice.ai) — a gateway, not a router.
        # It bills US dollars: the API reference describes every
        # model_spec.pricing field as "USD cost per million input tokens"
        # (docs.venice.ai/api-reference/endpoint/models/list), and its
        # pricing page opens "Prices per 1M tokens unless noted. All
        # prices in USD." (docs.venice.ai/overview/pricing).
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
    "xai": {
        "name": "xAI",
        "pages": ("global",),
        "sellerKind": "first-party",
        "source": XAI_PRICING_URL,
        # xAI's pricing doc opens "All prices are in USD" and its text-API
        # table bills "Input / 1M tokens", "Cached input / 1M tokens", and
        # "Output / 1M tokens" (docs.x.ai/developers/pricing.md), so the
        # published rates are US dollars per million tokens.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "mistral": {
        "name": "Mistral AI",
        "pages": ("global",),
        "sellerKind": "first-party",
        "source": MISTRAL_PRICING_URL,
        # Every rate on Mistral's API-pricing markdown is dollar-prefixed
        # ("Input $0.68 /M Tokens (sale price, regular $1.36)"), and the
        # rendered page's currency toggle opens on USD
        # (docs.mistral.ai/inference/pricing/), so the published rates are
        # US dollars per million tokens.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
    "meta": {
        "name": "Meta",
        "pages": ("global",),
        "sellerKind": "first-party",
        "source": META_PRICING_URL,
        # Every token rate in Meta's pricing markdown is dollar-prefixed in
        # columns labeled "Standard mode (per 1M tokens)" and "Contributor
        # mode (per 1M tokens)" ("| Input | $4.00 | Not available |",
        # dev.meta.ai/docs/pricing-rate-limits.md), and the docs publish no
        # other currency, so the published rates are US dollars per million
        # tokens.
        "nativeCurrency": "USD",
        "euClaim": "No EU routing catalog is published.",
    },
}
