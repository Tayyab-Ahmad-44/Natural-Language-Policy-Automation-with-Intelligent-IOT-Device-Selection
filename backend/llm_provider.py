"""
Single choke point for which LLM backend serves chat-completion calls
(policy parsing, task breakdown, device-catalog mapping, conflict judging).

Set LLM_PROVIDER=groq or LLM_PROVIDER=openai in .env to choose. Defaults to
"groq" to preserve existing behavior for anyone who hasn't set it. Each
provider reads its own API key (GROQ_API_KEY / OPENAI_API_KEY) and has a
default model, overridable via LLM_MODEL.

Groq's Python SDK deliberately mirrors OpenAI's chat.completions interface,
so callers in llm.py/conflicts.py don't need per-provider branches for most
parameters -- they call `create_chat_completion(...)` below the same way
regardless of which provider is configured. The one parameter that does
differ: newer OpenAI models (the gpt-5 family, o1/o3, ...) reject the
legacy `max_tokens` and require `max_completion_tokens` instead, while
Groq's API still only accepts `max_tokens`. create_chat_completion() picks
the right kwarg name so callers don't have to know which provider is active.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

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

# OpenAI's newer models (gpt-5 family, o1/o3, ...) renamed max_tokens to
# max_completion_tokens and reject the old name outright; Groq's API still
# only accepts max_tokens.
_MAX_TOKENS_KWARG = "max_completion_tokens" if LLM_PROVIDER == "openai" else "max_tokens"


def create_chat_completion(
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
):
    """chat.completions.create() with the provider-correct token-limit kwarg."""
    kwargs: Dict[str, Any] = {"model": MODEL, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs[_MAX_TOKENS_KWARG] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    return client.chat.completions.create(**kwargs)
