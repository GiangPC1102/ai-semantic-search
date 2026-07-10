"""LLM gateway via LiteLLM — hỗ trợ đổi provider (OpenAI, Gemini, Qwen, ...) chỉ bằng config."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import litellm
from litellm import ModelResponse

from app.core.config import BaseConfig, settings
from app.core.logger import logger

# LiteLLM model prefix theo provider
_PROVIDER_MODEL_PREFIX: dict[str, str] = {
    "openai": "openai",
    "gemini": "gemini",
    "qwen": "dashscope",
    "anthropic": "anthropic",
}

# Env var chứa API key tương ứng từng provider
_PROVIDER_API_KEY_ATTR: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass(frozen=True)
class LLMResponse:
    """Kết quả trả về chuẩn hóa từ LiteLLM."""

    content: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    raw: ModelResponse | None = None


class LLMError(Exception):
    """Lỗi khi gọi LLM gateway."""


class LLM:
    """Gateway gọi LLM qua LiteLLM.

    Mặc định dùng OpenAI. Đổi sang Gemini/Qwen bằng cách sửa ``LLM_PROVIDER``
    và ``LLM_MODEL`` trong ``.env`` — không cần sửa code gọi.

    Ví dụ:
        llm = LLM()
        response = llm.chat([{"role": "user", "content": "Xin chào"}])
        print(response.content)
    """

    def __init__(
        self,
        config: BaseConfig | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self._config = config or settings
        self.provider = (provider or self._config.LLM_PROVIDER).lower()
        self.model = model or self._config.LLM_MODEL
        self.temperature = (
            temperature if temperature is not None else self._config.LLM_TEMPERATURE
        )
        self.max_tokens = max_tokens or self._config.LLM_MAX_TOKENS
        self.timeout = timeout or self._config.LLM_TIMEOUT
        self._api_key = api_key or self._resolve_api_key()
        self._litellm_model = self._resolve_litellm_model()

        self._configure_litellm()

    def _resolve_api_key(self) -> str:
        """Lấy API key theo provider từ config hoặc biến môi trường."""
        attr = _PROVIDER_API_KEY_ATTR.get(self.provider)
        if not attr:
            raise LLMError(
                f"Provider '{self.provider}' chưa được hỗ trợ. "
                f"Các provider hợp lệ: {sorted(_PROVIDER_API_KEY_ATTR)}"
            )

        key = getattr(self._config, attr, "") or os.getenv(attr, "")
        if not key:
            raise LLMError(
                f"Thiếu API key cho provider '{self.provider}'. "
                f"Đặt biến môi trường {attr} trong .env"
            )
        return key

    def _resolve_litellm_model(self) -> str:
        """Chuẩn hóa tên model theo format LiteLLM (vd: openai/gpt-4o-mini)."""
        if "/" in self.model:
            return self.model

        prefix = _PROVIDER_MODEL_PREFIX.get(self.provider)
        if prefix:
            return f"{prefix}/{self.model}"
        return self.model

    def _configure_litellm(self) -> None:
        """Thiết lập API key và timeout cho LiteLLM."""
        env_key = _PROVIDER_API_KEY_ATTR.get(self.provider)
        if env_key:
            os.environ[env_key] = self._api_key

        litellm.request_timeout = self.timeout
        litellm.drop_params = True

        logger.debug(
            "LLM gateway initialized: provider=%s model=%s",
            self.provider,
            self._litellm_model,
        )

    def _build_kwargs(self, **overrides: Any) -> dict[str, Any]:
        """Gom tham số gọi completion, cho phép override từng lần gọi."""
        kwargs: dict[str, Any] = {
            "model": self._litellm_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "api_key": self._api_key,
        }
        kwargs.update(overrides)
        return kwargs

    @staticmethod
    def _parse_response(response: ModelResponse) -> LLMResponse:
        """Chuyển ModelResponse của LiteLLM sang LLMResponse nội bộ."""
        if not response.choices:
            raise LLMError("LLM trả về response rỗng (không có choices)")

        choice = response.choices[0]
        message = choice.message
        content = message.content or ""

        usage: dict[str, int] | None = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=content,
            model=response.model or "",
            finish_reason=choice.finish_reason,
            usage=usage,
            raw=response,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Gọi chat completion đồng bộ.

        Args:
            messages: Danh sách message OpenAI format
                ``[{"role": "system"|"user"|"assistant", "content": "..."}]``.
            **kwargs: Override tham số LiteLLM (temperature, max_tokens, ...).

        Returns:
            LLMResponse với nội dung text và metadata usage.
        """
        try:
            response = litellm.completion(
                messages=messages,
                **self._build_kwargs(**kwargs),
            )
            return self._parse_response(response)
        except Exception as exc:
            logger.error("LLM chat failed: %s", exc)
            raise LLMError(f"Gọi LLM thất bại: {exc}") from exc

    def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream text từng chunk (đồng bộ)."""
        try:
            response = litellm.completion(
                messages=messages,
                stream=True,
                **self._build_kwargs(**kwargs),
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            logger.error("LLM stream failed: %s", exc)
            raise LLMError(f"Stream LLM thất bại: {exc}") from exc

    def complete(self, prompt: str, system: str | None = None, **kwargs: Any) -> LLMResponse:
        """Shortcut: gửi một prompt đơn giản."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)
