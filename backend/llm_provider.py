"""
Single choke point for which LLM backend serves chat-completion calls
(policy parsing, task breakdown, device-catalog mapping, conflict judging).

Set LLM_PROVIDER=groq or LLM_PROVIDER=openai in .env to choose. Defaults to
"groq" to preserve existing behavior for anyone who hasn't set it. Each
provider reads its own API key (GROQ_API_KEY / OPENAI_API_KEY) and has a
default model, overridable via LLM_MODEL.

Groq's Python SDK deliberately mirrors OpenAI's chat.completions interface,
so callers in llm.py/conflicts.py don't need per-provider branches -- they
just call `llm_provider.client.chat.completions.create(model=llm_provider.MODEL, ...)`
the same way regardless of which provider is configured.
"""

from __future__ import annotations

import os

from load_dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()

_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-5.4-mini",
}

if LLM_PROVIDER not in _DEFAULT_MODELS:
    raise ValueError(
        f"Unknown LLM_PROVIDER '{LLM_PROVIDER}' -- expected one of {sorted(_DEFAULT_MODELS)}"
    )


def _build_client():
    if LLM_PROVIDER == "openai":
        from openai import OpenAI
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    from groq import Groq
    return Groq(api_key=os.getenv("GROQ_API_KEY"))


client = _build_client()
MODEL = os.getenv("LLM_MODEL") or _DEFAULT_MODELS[LLM_PROVIDER]
