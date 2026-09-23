from unittest.mock import MagicMock

import httpx
import pytest

from app.providers import AnthropicProvider, LLMProviderError

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _response(status_code: int, json: dict) -> httpx.Response:
    return httpx.Response(status_code, request=REQUEST, json=json)


def _make_provider() -> AnthropicProvider:
    provider = AnthropicProvider(api_key="test-key")
    provider._client = MagicMock()
    return provider


def test_complete_success() -> None:
    provider = _make_provider()
    provider._client.post.return_value = _response(200, {"content": [{"type": "text", "text": "hi"}]})

    result = provider.complete([{"role": "user", "content": "hello"}])

    assert result.content == "hi"
    assert result.tool_calls == []


def test_complete_invalid_credentials() -> None:
    provider = _make_provider()
    provider._client.post.return_value = _response(401, {"error": {"message": "boom"}})

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 401


def test_complete_timeout() -> None:
    provider = _make_provider()
    provider._client.post.side_effect = httpx.TimeoutException("timed out", request=REQUEST)

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 504


def test_complete_malformed_response() -> None:
    provider = _make_provider()
    provider._client.post.return_value = _response(200, {"unexpected": "shape"})

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 502


def test_complete_provider_failure() -> None:
    provider = _make_provider()
    provider._client.post.return_value = _response(500, {"error": {"message": "boom"}})

    with pytest.raises(LLMProviderError) as exc:
        provider.complete([{"role": "user", "content": "hi"}])
    assert exc.value.status_code == 502
