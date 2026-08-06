from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from core.config import load_settings, normalized_provider, require_llm_credentials
from retrieval.agent import SYSTEM_PROMPT
from retrieval.llm import build_llm


@pytest.mark.parametrize(
    ("provider", "field", "value"),
    [
        ("gemini", "google_api_key", "google-test"),
        ("openai", "openai_api_key", "openai-test"),
        ("anthropic", "anthropic_api_key", "anthropic-test"),
        ("openrouter", "openrouter_api_key", "openrouter-test"),
        ("custom", "custom_llm_base_url", "https://llm.example/v1"),
    ],
)
def test_supported_remote_providers_accept_their_credentials(provider, field, value):
    settings = replace(load_settings(), llm_provider=provider, **{field: value})
    require_llm_credentials(settings)


def test_ollama_does_not_require_api_key():
    settings = replace(load_settings(), llm_provider="ollama")
    require_llm_credentials(settings)


def test_provider_aliases_are_normalized():
    assert normalized_provider(replace(load_settings(), llm_provider="Custom-LLM")) == "custom"
    assert normalized_provider(replace(load_settings(), llm_provider="anthorpic")) == "anthropic"


def test_unknown_provider_is_rejected():
    settings = replace(load_settings(), llm_provider="unknown")
    with pytest.raises(RuntimeError, match="Unsupported"):
        require_llm_credentials(settings)


def test_agent_prompt_forbids_inferred_metadata():
    assert "Never infer, guess, enrich" in SYSTEM_PROMPT
    assert "If it is `uncategorized`, answer `uncategorized`" in SYSTEM_PROMPT
    assert "do not propose broader, plausible, or inferred categories" in SYSTEM_PROMPT


@patch("retrieval.llm.ChatGoogleGenerativeAI")
def test_gemini_maps_model_key_and_temperature(chat):
    settings = replace(
        load_settings(),
        llm_provider="gemini",
        model_name="gemini-test",
        google_api_key="secret-test-value",
    )
    build_llm(settings, temperature=0.2)
    chat.assert_called_once_with(
        model="gemini-test",
        google_api_key="secret-test-value",
        temperature=0.2,
    )
