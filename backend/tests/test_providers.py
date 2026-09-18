from unittest.mock import MagicMock

import httpx
import pytest

from app.providers import GroqProvider, LLMProviderError

REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _status_error(cls, status_code: int):
    response = httpx.Response(status_code, request=REQUEST, json={"error": {"message": "boom"}})
    return cls("boom", response=response, body=None)


def _make_provider() -> GroqProvider:
    provider = GroqProvider(api_key="test-key")
    provider._client = MagicMock()
    return provider


def test_complete_success() -> None:
    import groq

    provider = _make_provider()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content="hi", tool_calls=None))]
    provider._client.chat.completions.create.return_value = completion

    result = provider.complete([{"role": "user", "content": "hello"}])

    assert result.content == "hi"
    assert result.tool_calls == []


def test_complete_invalid_credentials() -> None:
    import groq

    provider = _make_provider()
    provider._client.chat.completions.create.side_effect = _status_error(groq.AuthenticationError, 401)

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 401


def test_complete_timeout() -> None:
    import groq

    provider = _make_provider()
    provider._client.chat.completions.create.side_effect = groq.APITimeoutError(request=REQUEST)

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 504


def test_complete_malformed_response() -> None:
    provider = _make_provider()
    completion = MagicMock()
    completion.choices = []
    provider._client.chat.completions.create.return_value = completion

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 502


def test_complete_provider_failure() -> None:
    import groq

    provider = _make_provider()
    provider._client.chat.completions.create.side_effect = _status_error(groq.InternalServerError, 500)

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 502
