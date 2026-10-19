"""Source registry for the shared fetch layer.

Each entry describes one pricing source and declares which page(s) it feeds
via `pages`. Today every source feeds only the EU router page, and the build
step does not branch on `pages` yet.
"""

from fetch_providers import DEEPSEEK_URL, ZAI_PAYGO_URL
from sources.claude_direct import CLAUDE_MODELS_URL, CLAUDE_PRICING_URL
from sources.cortecs import CORTECS_URL
from sources.eurouter import EUROUTER_URL
from sources.openai_direct import OPENAI_MODELS_URL, OPENAI_PRICING_URL
from sources.opencode import OPENCODE_ZEN_URL
from sources.openrouter import OPENROUTER_URL

SOURCES = {
    "cortecs": {
        "name": "Cortecs",
        "pages": ("router",),
        "source": CORTECS_URL,
        "euClaim": "EU catalog: providers based and regulated within the EU.",
    },
    "eurouter": {
        "name": "EUrouter",
        "pages": ("router",),
        "source": EUROUTER_URL,
        "euClaim": "EU handling is EUrouter's baseline routing guarantee.",
    },
    "openrouter": {
        "name": "OpenRouter",
        "pages": ("router",),
        "source": OPENROUTER_URL,
        "euClaim": "EU regional routing; Business or Enterprise plan required.",
    },
    "opencode": {
        "name": "OpenCode Zen",
        "pages": ("router",),
        "source": OPENCODE_ZEN_URL,
        "euClaim": "No EU routing catalog is published.",
    },
    "deepseek-direct": {
        "name": "DeepSeek API",
        "pages": ("router",),
        "source": DEEPSEEK_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "zai-direct": {
        "name": "z.ai API",
        "pages": ("router",),
        "source": ZAI_PAYGO_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "claude-direct": {
        "name": "Claude API",
        "pages": ("router",),
        "source": CLAUDE_PRICING_URL,
        "catalogSource": CLAUDE_MODELS_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
    "openai-direct": {
        "name": "OpenAI API",
        "pages": ("router",),
        "source": OPENAI_PRICING_URL,
        "catalogSource": OPENAI_MODELS_URL,
        "kind": "direct",
        "euClaim": "Direct API baseline; no router or EU routing mode.",
    },
}
