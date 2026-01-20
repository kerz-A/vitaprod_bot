"""
GigaChat LLM provider implementation.
Uses Sber's GigaChat API (free tier available).
"""

from typing import AsyncIterator

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from src.config import settings
from src.integrations.llm.base import BaseLLM, LLMResponse


class GigaChatLLM(BaseLLM):
    """GigaChat LLM provider."""

    def __init__(
        self,
        credentials: str | None = None,
        scope: str | None = None,
    ):
        self.credentials = credentials or settings.gigachat_credentials
        self.scope = scope or settings.gigachat_scope

        if not self.credentials:
            raise ValueError(
                "GigaChat credentials not provided. "
                "Set GIGACHAT_CREDENTIALS in .env file."
            )

    def _get_client(self) -> GigaChat:
        """Create GigaChat client."""
        return GigaChat(
            credentials=self.credentials,
            scope=self.scope,
            verify_ssl_certs=False,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate response using GigaChat."""
        messages = []

        if system_prompt:
            messages.append(
                Messages(role=MessagesRole.SYSTEM, content=system_prompt)
            )

        messages.append(Messages(role=MessagesRole.USER, content=prompt))

        with self._get_client() as client:
            response = client.chat(
                Chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

        return LLMResponse(
            content=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens if response.usage else None,
            model=response.model,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream response from GigaChat."""
        messages = []

        if system_prompt:
            messages.append(
                Messages(role=MessagesRole.SYSTEM, content=system_prompt)
            )

        messages.append(Messages(role=MessagesRole.USER, content=prompt))

        with self._get_client() as client:
            for chunk in client.stream(
                Chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            ):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    @property
    def name(self) -> str:
        return "gigachat"
