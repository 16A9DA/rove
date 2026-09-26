from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("rove.providers")

# ponytail: flat constant. Vision completions (image tokens) run slower than text-only —
# raise further if screenshot-heavy runs still hit a timeout.
DEFAULT_TIMEOUT = 60.0

ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_DEFAULT_MAX_TOKENS = 4096
ANTHROPIC_DEFAULT_MAX_RETRIES = 3
ANTHROPIC_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

OPENAI_DEFAULT_MODEL = "gpt-4o"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
# Models API lists every OpenAI model, chat and non-chat alike — filter down to what
# this agent loop could actually call (skips embeddings/audio/image/moderation models).
_OPENAI_NON_CHAT_MARKERS = ("embedding", "whisper", "tts", "dall-e", "moderation", "davinci-002", "babbage-002", "audio")


class LLMProviderError(Exception):
    """Raised when a provider call fails. `status_code` maps to the HTTP response."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


def _data_uri_to_media(url: str) -> tuple[str, str]:
    # "data:image/jpeg;base64,<data>" -> ("image/jpeg", "<data>")
    header, data = url.split(",", 1)
    media_type = header.removeprefix("data:").split(";")[0]
    return media_type, data


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """Anthropic's Messages API doesn't use OpenAI-shaped roles: system is a top-level
    field, tool calls/results are content blocks on user/assistant turns, not a separate
    'tool' role — this is the one real translation layer needed, since tool schemas are
    still built in OpenAI shape (ToolRegistry.to_openai_tools)."""
    system: str | None = None
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system = m["content"] if system is None else f"{system}\n\n{m['content']}"
        elif role == "user":
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
            else:
                blocks = []
                for block in content:
                    if block["type"] == "text":
                        blocks.append({"type": "text", "text": block["text"]})
                    elif block["type"] == "image_url":
                        media_type, data = _data_uri_to_media(block["image_url"]["url"])
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
                out.append({"role": "user", "content": blocks})
        elif role == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []):
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": json.loads(tc["function"]["arguments"] or "{}")})
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            out.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}]})
    return system, out


def _to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]} for t in tools]


class AnthropicProvider(LLMProvider):
    """Talks to Anthropic's Messages API directly over httpx — no SDK dependency.
    Anthropic's own message/tool shape (not OpenAI's) means the request/response need
    real translation (see _to_anthropic_messages/_to_anthropic_tools) rather than a
    pass-through."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = ANTHROPIC_DEFAULT_MAX_RETRIES,
    ) -> None:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY is not set", status_code=500)
        self.model = model or os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL)
        self._max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_API_VERSION},
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        system, anthropic_messages = _to_anthropic_messages(messages)
        logger.info("anthropic request model=%s messages=%d tools=%d", self.model, len(anthropic_messages), len(tools or []))
        payload: dict[str, Any] = {"model": self.model, "max_tokens": ANTHROPIC_DEFAULT_MAX_TOKENS, "messages": anthropic_messages}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = _to_anthropic_tools(tools)

        response = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(ANTHROPIC_BASE_URL, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMProviderError("Anthropic request timed out", status_code=504) from exc
            except httpx.RequestError as exc:
                raise LLMProviderError("could not reach Anthropic", status_code=502) from exc

            if response.status_code == 200:
                break
            if response.status_code in (429, 503, 529) and attempt < self._max_retries:
                retry_after = float(response.headers.get("retry-after", ANTHROPIC_BACKOFF_SECONDS[attempt]))
                time.sleep(min(retry_after, ANTHROPIC_BACKOFF_SECONDS[attempt]))
                continue
            if response.status_code == 401:
                raise LLMProviderError("invalid Anthropic credentials", status_code=401)
            if response.status_code == 429:
                raise LLMProviderError("Anthropic rate limit exceeded", status_code=429)
            if response.status_code == 400:
                raise LLMProviderError("malformed request to Anthropic", status_code=400)
            raise LLMProviderError(f"Anthropic API error ({response.status_code})", status_code=502)
        assert response is not None

        try:
            body = response.json()
            blocks = body["content"]
        except (KeyError, ValueError) as exc:
            raise LLMProviderError("malformed response from Anthropic", status_code=502) from exc

        text_parts = [b["text"] for b in blocks if b["type"] == "text"]
        tool_calls = [ToolCall(id=b["id"], name=b["name"], arguments=json.dumps(b["input"])) for b in blocks if b["type"] == "tool_use"]
        logger.info("anthropic response tool_calls=%d", len(tool_calls))
        return LLMResponse(content="\n".join(text_parts) if text_parts else None, tool_calls=tool_calls)


def list_anthropic_models(api_key: str) -> list[dict[str, str]]:
    response = httpx.get(ANTHROPIC_MODELS_URL, headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_API_VERSION}, timeout=10.0)
    if response.status_code == 401:
        raise LLMProviderError("invalid Anthropic credentials", status_code=401)
    if response.status_code != 200:
        raise LLMProviderError(f"Anthropic API error ({response.status_code})", status_code=502)
    return [{"id": m["id"], "display_name": m.get("display_name", m["id"])} for m in response.json().get("data", [])]


def list_openai_models(api_key: str) -> list[dict[str, str]]:
    response = httpx.get(OPENAI_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0)
    if response.status_code == 401:
        raise LLMProviderError("invalid OpenAI credentials", status_code=401)
    if response.status_code != 200:
        raise LLMProviderError(f"OpenAI API error ({response.status_code})", status_code=502)
    ids = sorted(m["id"] for m in response.json().get("data", []) if not any(marker in m["id"] for marker in _OPENAI_NON_CHAT_MARKERS))
    return [{"id": i, "display_name": i} for i in ids]


class OpenAIProvider(LLMProvider):
    """OpenAI's Chat Completions API. Messages/tools already flow through this codebase
    in OpenAI's own shape (ToolRegistry.to_openai_tools; tool/assistant roles built in
    app/agents/base.py) since that shape was the original design — unlike
    AnthropicProvider, this is a near-passthrough with no translation layer."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = ANTHROPIC_DEFAULT_MAX_RETRIES,
    ) -> None:
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMProviderError("OPENAI_API_KEY is not set", status_code=500)
        self.model = model or os.environ.get("OPENAI_MODEL", OPENAI_DEFAULT_MODEL)
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        logger.info("openai request model=%s messages=%d tools=%d", self.model, len(messages), len(tools or []))
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools

        response = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(OPENAI_CHAT_URL, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMProviderError("OpenAI request timed out", status_code=504) from exc
            except httpx.RequestError as exc:
                raise LLMProviderError("could not reach OpenAI", status_code=502) from exc

            if response.status_code == 200:
                break
            if response.status_code in (429, 500, 503) and attempt < self._max_retries:
                time.sleep(ANTHROPIC_BACKOFF_SECONDS[attempt])
                continue
            if response.status_code == 401:
                raise LLMProviderError("invalid OpenAI credentials", status_code=401)
            if response.status_code == 429:
                raise LLMProviderError("OpenAI rate limit exceeded", status_code=429)
            if response.status_code == 400:
                raise LLMProviderError("malformed request to OpenAI", status_code=400)
            raise LLMProviderError(f"OpenAI API error ({response.status_code})", status_code=502)
        assert response is not None

        try:
            message = response.json()["choices"][0]["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMProviderError("malformed response from OpenAI", status_code=502) from exc

        tool_calls = [
            ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=tc["function"]["arguments"])
            for tc in message.get("tool_calls") or []
        ]
        logger.info("openai response tool_calls=%d", len(tool_calls))
        return LLMResponse(content=message.get("content"), tool_calls=tool_calls)
