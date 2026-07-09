"""Curated LLM model catalog for Settings and Copilot.

Auth is per *provider* (one API key). Models are choices under a connected
provider. Catalog is versioned in code — not live-fetched — so tool-calling
reliability stays under our control. Exact $/M prices drift; cost_band is the
stable UX signal.
"""

from __future__ import annotations

from typing import Any

CATALOG_VERSION = "2026-07-09"

# cost_band: $ cheapest … $$$$ most expensive (relative, not billing)
CostBand = str


def _model(
    *,
    id: str,
    label: str,
    cost_band: CostBand,
    blurb: str,
    recommended: bool = False,
    price_hint: str = "",
    tools: bool = True,
    cheap: bool = False,
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "cost_band": cost_band,
        "blurb": blurb,
        "recommended": recommended,
        "price_hint": price_hint,  # e.g. "$2 / $6 per 1M in/out" when known
        "tools": tools,
        "cheap": cheap,
    }


PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "xai": {
        "id": "xai",
        "label": "xAI",
        "hint": "Grok family",
        "default_model": "grok-4.5",
        "default_base_url": "https://api.x.ai/v1",
        "auth_note": "One xAI API key unlocks every Grok model below.",
        "models": [
            _model(
                id="grok-4.5",
                label="Grok 4.5",
                cost_band="$$$",
                blurb="Flagship · tools & reasoning",
                recommended=True,
                price_hint="$2 / $6 per 1M",
            ),
            _model(
                id="grok-4.3",
                label="Grok 4.3",
                cost_band="$$",
                blurb="Strong general chat",
                price_hint="$1.25 / $2.50 per 1M",
            ),
            _model(
                id="grok-4.20-0309-reasoning",
                label="Grok 4.20 Reasoning",
                cost_band="$$",
                blurb="Deeper multi-step reasoning",
                price_hint="$1.25 / $2.50 per 1M",
            ),
            _model(
                id="grok-4.20-0309-non-reasoning",
                label="Grok 4.20 Fast",
                cost_band="$$",
                blurb="Faster responses",
                price_hint="$1.25 / $2.50 per 1M",
                cheap=True,
            ),
            _model(
                id="grok-4.20-multi-agent-0309",
                label="Grok 4.20 Multi-agent",
                cost_band="$$",
                blurb="Built-in multi-agent",
                price_hint="$1.25 / $2.50 per 1M",
            ),
        ],
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "hint": "GPT family",
        "default_model": "gpt-5.5",
        "default_base_url": "https://api.openai.com/v1",
        "auth_note": "One OpenAI API key unlocks the models below.",
        "models": [
            _model(
                id="gpt-5.5",
                label="GPT-5.5",
                cost_band="$$$",
                blurb="Latest flagship",
                recommended=True,
            ),
            _model(
                id="gpt-5-mini",
                label="GPT-5 mini",
                cost_band="$$",
                blurb="Cheaper everyday chat",
                cheap=True,
            ),
            _model(
                id="gpt-4.1",
                label="GPT-4.1",
                cost_band="$$$",
                blurb="Stable tools-capable",
            ),
            _model(
                id="gpt-4.1-mini",
                label="GPT-4.1 mini",
                cost_band="$$",
                blurb="Fast / lower cost",
                cheap=True,
            ),
            _model(
                id="gpt-4o-mini",
                label="GPT-4o mini",
                cost_band="$",
                blurb="Very cheap tools model",
                cheap=True,
                price_hint="~$0.15 / $0.60 per 1M",
            ),
        ],
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Anthropic",
        "hint": "Claude family",
        "default_model": "claude-opus-4-7",
        "default_base_url": "https://api.anthropic.com/v1",
        "auth_note": "One Anthropic API key unlocks Claude models below.",
        "models": [
            _model(
                id="claude-opus-4-7",
                label="Claude Opus 4.7",
                cost_band="$$$$",
                blurb="Highest capability",
                recommended=True,
            ),
            _model(
                id="claude-sonnet-4-5",
                label="Claude Sonnet 4.5",
                cost_band="$$$",
                blurb="Balanced quality & cost",
            ),
            _model(
                id="claude-haiku-4-5",
                label="Claude Haiku 4.5",
                cost_band="$",
                blurb="Fast / economical",
                cheap=True,
            ),
        ],
    },
    "gemini": {
        "id": "gemini",
        "label": "Google Gemini",
        "hint": "Gemini family",
        "default_model": "gemini-3.1-flash-lite",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "auth_note": "One Gemini API key unlocks models below.",
        "models": [
            _model(
                id="gemini-3.1-flash-lite",
                label="Gemini 3.1 Flash Lite",
                cost_band="$",
                blurb="Fast & cheap",
                recommended=True,
                cheap=True,
            ),
            _model(
                id="gemini-3.1-flash",
                label="Gemini 3.1 Flash",
                cost_band="$$",
                blurb="Balanced",
                cheap=True,
            ),
            _model(
                id="gemini-3.1-pro",
                label="Gemini 3.1 Pro",
                cost_band="$$$",
                blurb="Higher quality",
            ),
        ],
    },
    "openrouter": {
        "id": "openrouter",
        "label": "OpenRouter",
        "hint": "Many models · one key · great for cheap options",
        "default_model": "openrouter/auto",
        "default_base_url": "https://openrouter.ai/api/v1",
        "auth_note": (
            "One OpenRouter key routes to many providers. Ideal for very cheap "
            "capable models without managing each vendor key."
        ),
        "models": [
            _model(
                id="openrouter/auto",
                label="OpenRouter Auto",
                cost_band="$",
                blurb="Router picks a capable cheap model",
                recommended=True,
                cheap=True,
            ),
            _model(
                id="deepseek/deepseek-chat",
                label="DeepSeek Chat",
                cost_band="$",
                blurb="Strong & very cheap",
                cheap=True,
                price_hint="Often well under $1 / 1M",
            ),
            _model(
                id="google/gemini-2.0-flash-001",
                label="Gemini 2.0 Flash",
                cost_band="$",
                blurb="Fast via OpenRouter",
                cheap=True,
            ),
            _model(
                id="meta-llama/llama-3.3-70b-instruct",
                label="Llama 3.3 70B",
                cost_band="$",
                blurb="Open weights · low cost",
                cheap=True,
            ),
            _model(
                id="qwen/qwen-2.5-72b-instruct",
                label="Qwen 2.5 72B",
                cost_band="$",
                blurb="Capable open model",
                cheap=True,
            ),
            _model(
                id="mistralai/mistral-small-3.1-24b-instruct",
                label="Mistral Small",
                cost_band="$",
                blurb="Economical tools chat",
                cheap=True,
            ),
            _model(
                id="openai/gpt-4o-mini",
                label="GPT-4o mini (via OR)",
                cost_band="$",
                blurb="Cheap OpenAI-class tools",
                cheap=True,
            ),
            _model(
                id="anthropic/claude-3.5-haiku",
                label="Claude Haiku (via OR)",
                cost_band="$$",
                blurb="Fast Claude-class",
                cheap=True,
            ),
            _model(
                id="x-ai/grok-3-mini",
                label="Grok mini (via OR)",
                cost_band="$$",
                blurb="When available on OpenRouter",
                cheap=True,
            ),
        ],
    },
    "custom_openai_compatible": {
        "id": "custom_openai_compatible",
        "label": "Custom (OpenAI-compatible)",
        "hint": "Ollama, LM Studio, proxies",
        "default_model": "",
        "default_base_url": "",
        "auth_note": "Point at any OpenAI-compatible endpoint. Key optional for local servers.",
        "models": [],
    },
}


def list_provider_ids() -> list[str]:
    return list(PROVIDER_CATALOG.keys())


def get_provider_entry(provider: str) -> dict[str, Any] | None:
    return PROVIDER_CATALOG.get(str(provider or "").strip().lower())


def default_model_for_catalog_provider(provider: str) -> str:
    entry = get_provider_entry(provider)
    if not entry:
        return ""
    return str(entry.get("default_model") or "")


def default_base_url_for_catalog_provider(provider: str) -> str:
    entry = get_provider_entry(provider)
    if not entry:
        return ""
    return str(entry.get("default_base_url") or "")


def models_for_provider(provider: str) -> list[dict[str, Any]]:
    entry = get_provider_entry(provider)
    if not entry:
        return []
    return list(entry.get("models") or [])


def find_model(provider: str, model_id: str) -> dict[str, Any] | None:
    target = str(model_id or "").strip()
    for model in models_for_provider(provider):
        if model.get("id") == target:
            return model
    return None


def normalize_conversation_llm(
    raw: dict[str, Any] | None,
    *,
    fallback_provider: str,
    fallback_model: str,
) -> dict[str, Any]:
    """Resolve conversation override or workspace default."""
    provider = str(fallback_provider or "openai").strip().lower()
    model = str(fallback_model or "").strip()
    source = "workspace_default"
    if isinstance(raw, dict):
        p = str(raw.get("provider") or "").strip().lower()
        m = str(raw.get("model") or "").strip()
        if p:
            provider = p
        if m:
            model = m
            source = "conversation"
    if not model:
        model = default_model_for_catalog_provider(provider) or model
    meta = find_model(provider, model) or {}
    return {
        "provider": provider,
        "model": model,
        "label": meta.get("label") or model,
        "cost_band": meta.get("cost_band") or "",
        "source": source,
        "cheap": bool(meta.get("cheap")),
    }


def build_llm_options_payload(
    *,
    active_provider: str,
    active_model: str,
    connected_providers: list[dict[str, Any]],
    conversation_llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Payload for GET /api/copilot/llm-options and Settings bootstrap."""
    providers_out: list[dict[str, Any]] = []
    connected_ids = {
        str(item.get("id") or "").strip().lower()
        for item in connected_providers
        if item.get("connected")
    }
    for provider_id, entry in PROVIDER_CATALOG.items():
        connected = provider_id in connected_ids
        providers_out.append(
            {
                "id": provider_id,
                "label": entry["label"],
                "hint": entry.get("hint") or "",
                "default_model": entry.get("default_model") or "",
                "default_base_url": entry.get("default_base_url") or "",
                "auth_note": entry.get("auth_note") or "",
                "connected": connected,
                "models": entry.get("models") or [],
            }
        )
    resolved = normalize_conversation_llm(
        conversation_llm,
        fallback_provider=active_provider,
        fallback_model=active_model,
    )
    return {
        "catalog_version": CATALOG_VERSION,
        "active_provider": str(active_provider or "").strip().lower(),
        "active_model": str(active_model or "").strip(),
        "resolved": resolved,
        "connected_providers": connected_providers,
        "providers": providers_out,
    }
