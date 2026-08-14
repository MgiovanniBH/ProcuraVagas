"""Tests for LLM factory, NVIDIA NIM integration, and budget enforcement."""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from job_scout.config import Settings
from job_scout.llm import (
    LLMBudgetExceededError,
    ensure_budget,
    get_chat_model,
    get_nvidia_client,
)


def test_get_chat_model_nvidia(monkeypatch):
    """NVIDIA models should instantiate ChatOpenAI pointing to NVIDIA base URL."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-12345")
    # Clear lru_cache
    get_chat_model.cache_clear()

    model = get_chat_model("nvidia:nvidia/nemotron-3.5-lightning-30b-a3b", temperature=0.7)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert model.openai_api_base == "https://integrate.api.nvidia.com/v1"
    assert model.max_tokens == 524288
    assert model.temperature == 0.7
    assert model.extra_body == {
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 524288,
    }


def test_get_chat_model_nvidia_slash_syntax(monkeypatch):
    """Model strings starting directly with nvidia/ should also route to NVIDIA NIM."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-67890")
    get_chat_model.cache_clear()

    model = get_chat_model("nvidia/nemotron-3.5-lightning-30b-a3b", temperature=0.0)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert model.openai_api_base == "https://integrate.api.nvidia.com/v1"


def test_get_nvidia_client(monkeypatch):
    """Direct OpenAI client factory for NVIDIA NIM."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-direct-key")
    client = get_nvidia_client()
    assert str(client.base_url) == "https://integrate.api.nvidia.com/v1/"
    assert client.api_key == "nvapi-direct-key"


def test_ensure_budget():
    """Circuit breaker prevents runaway LLM calls."""
    ensure_budget(current_calls=5, planned=2, max_calls=10)

    with pytest.raises(LLMBudgetExceededError, match="exceeding MAX_LLM_CALLS_PER_RUN"):
        ensure_budget(current_calls=9, planned=2, max_calls=10)


def test_settings_nvidia_properties():
    """Settings should parse and expose NVIDIA config."""
    s = Settings(
        SCOUT_MODEL="nvidia:nvidia/nemotron-3.5-lightning-30b-a3b",
        NVIDIA_API_KEY="test-nv-key",
        NVIDIA_BASE_URL="https://custom.nvidia.endpoint/v1",
    )
    assert s.has_nvidia is True
    assert s.nvidia_api_key.get_secret_value() == "test-nv-key"
    assert s.nvidia_base_url == "https://custom.nvidia.endpoint/v1"


def test_auto_fallback_to_nvidia(monkeypatch):
    """When only NVIDIA_API_KEY is present, asking for default openai: model routes to NVIDIA."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fallback-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_chat_model.cache_clear()

    model = get_chat_model("openai:gpt-4o-mini", temperature=0.0)
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == "https://integrate.api.nvidia.com/v1"


def test_fetch_jobs_model_independent_fallback(monkeypatch, sample_profile):
    """fetch_jobs should never fail even if the LLM raises credentials or tool binding errors."""
    from job_scout.graph.nodes.fetch_jobs import fetch_jobs

    def failing_get_chat_model(*args, **kwargs):
        raise RuntimeError("LLM unavailable or invalid credentials")

    import job_scout.graph.nodes.fetch_jobs as fetch_mod
    monkeypatch.setattr(fetch_mod, "get_chat_model", failing_get_chat_model)

    state = {
        "profile": sample_profile,
        "jobs": [],
        "errors": [],
    }

    result = fetch_jobs(state)
    assert "jobs" in result
    assert "search_query" in result
    assert len(result["jobs"]) > 0
    assert any("fetch_jobs" in err for err in result["errors"])

