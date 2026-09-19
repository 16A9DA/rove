"""LLM provider abstraction and Groq implementation."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import groq

logger = logging.getLogger("rove.providers")

DEFAULT_MODEL = "openai/gpt-oss-120b"
# ponytail: flat constant. Vision completions (image tokens) run slower than text-only —
# raise further if screenshot-heavy runs still hit APITimeoutError.
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2


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


class GroqProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise LLMProviderError("GROQ_API_KEY is not set", status_code=500)
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self._client = groq.Groq(api_key=api_key, timeout=timeout, max_retries=max_retries)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        logger.info("groq request model=%s messages=%d tools=%d", self.model, len(messages), len(tools or []))
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or groq.NOT_GIVEN,
            )
        except groq.AuthenticationError as exc:
            raise LLMProviderError("invalid Groq credentials", status_code=401) from exc
        except groq.RateLimitError as exc:
            raise LLMProviderError("Groq rate limit exceeded", status_code=429) from exc
        except groq.APITimeoutError as exc:
            raise LLMProviderError("Groq request timed out", status_code=504) from exc
        except groq.BadRequestError as exc:
            raise LLMProviderError("malformed request to Groq", status_code=400) from exc
        except groq.APIStatusError as exc:
            raise LLMProviderError(f"Groq API error ({exc.status_code})", status_code=502) from exc
        except groq.APIConnectionError as exc:
            raise LLMProviderError("could not reach Groq", status_code=502) from exc

        try:
            message = completion.choices[0].message
        except (IndexError, AttributeError) as exc:
            raise LLMProviderError("malformed response from Groq", status_code=502) from exc

        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (message.tool_calls or [])
        ]
        logger.info("groq response tool_calls=%d", len(tool_calls))
        return LLMResponse(content=message.content, tool_calls=tool_calls)
