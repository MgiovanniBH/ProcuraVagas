"""Chat-model factory and the per-run LLM call budget.

The call budget is a simple circuit breaker: every node reads the running
``llm_calls`` counter from state, checks it against ``MAX_LLM_CALLS_PER_RUN``
before calling the model, and returns the incremented total. The graph runs
sequentially, so returning the cumulative total (not a delta) keeps the counter
correct.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from job_scout.config import get_settings


class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed ``MAX_LLM_CALLS_PER_RUN``."""


def _export_openai_key() -> None:
    """Copy the OpenAI key from settings into the environment for LangChain.

    ``pydantic-settings`` reads ``.env`` into the ``Settings`` object but does not
    export to ``os.environ``, which is where the OpenAI client looks for its key.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return
    key = get_settings().openai_api_key.get_secret_value()
    if key:
        os.environ["OPENAI_API_KEY"] = key


def _get_nvidia_key() -> str:
    """Get the NVIDIA key from environment or settings."""
    env_key = os.environ.get("NVIDIA_API_KEY")
    if env_key:
        return env_key
    settings_key = get_settings().nvidia_api_key.get_secret_value()
    if settings_key:
        os.environ["NVIDIA_API_KEY"] = settings_key
        return settings_key
    return ""


def get_nvidia_client():
    """Return an OpenAI client configured for NVIDIA NIM."""
    from openai import OpenAI

    settings = get_settings()
    api_key = _get_nvidia_key()
    base_url = settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1"
    return OpenAI(base_url=base_url, api_key=api_key or "missing-key")


DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


@lru_cache(maxsize=8)
def get_chat_model(model: str, temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for any provider string.

    Supports:
    - NVIDIA models: ``nvidia:<model_name>``, ``nvidia/<model_name>``, or models hosted on NVIDIA NIM
      (e.g. ``nvidia:nvidia/nemotron-3.5-lightning-30b-a3b``, ``meta/llama-3.3-70b-instruct``).
    - OpenAI models: ``openai:<model_name>`` (e.g. ``openai:gpt-4o-mini``).
    - Other LangChain providers supported by ``init_chat_model`` (e.g. ``groq:...``, ``ollama:...``).
    - Automatic provider fallback: if an OpenAI model is requested but only an NVIDIA API key is configured,
      automatically routes to NVIDIA NIM instead of failing.
    """
    settings = get_settings()
    nvidia_key = _get_nvidia_key()
    openai_key = settings.openai_api_key.get_secret_value() or os.environ.get("OPENAI_API_KEY", "")

    # Auto-fallback: if default openai model was kept but user only configured NVIDIA
    if model.startswith("openai:") and not openai_key and nvidia_key:
        model = f"nvidia:{DEFAULT_NVIDIA_MODEL}"

    # NVIDIA NIM routing
    is_nvidia = (
        model.startswith("nvidia:")
        or model.startswith("nvidia/")
        or "nemotron" in model.lower()
        or (bool(nvidia_key) and any(model.startswith(p) for p in ("meta/", "mistralai/", "deepseek-ai/")))
    )

    if is_nvidia:
        model_name = model.removeprefix("nvidia:")
        base_url = settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1"
        max_tokens = settings.nvidia_max_tokens

        extra_body: dict[str, Any] | None = None
        if "nemotron" in model_name.lower() or "reasoning" in model_name.lower():
            extra_body = {
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": max_tokens,
            }

        return ChatOpenAI(
            model=model_name,
            api_key=nvidia_key or None,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

    if model.startswith("openai:"):
        _export_openai_key()

    return init_chat_model(model, temperature=temperature)


def ensure_budget(current_calls: int, planned: int, max_calls: int) -> None:
    """Raise ``LLMBudgetExceededError`` if ``planned`` more calls would exceed ``max_calls``."""
    if current_calls + planned > max_calls:
        raise LLMBudgetExceededError(
            f"Run would make {current_calls + planned} LLM calls, exceeding MAX_LLM_CALLS_PER_RUN={max_calls}."
        )
