"""
Groq LLM provider implementation.
Uses Groq's FREE API with Llama models.

Free tier: ~6000 tokens/min, 30 req/min for Llama 3.3 70B.
Get API key: https://console.groq.com
"""

import logging
from typing import AsyncIterator

import aiohttp

from src.config import settings
from src.integrations.llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)


class GroqLLM(BaseLLM):
    """Groq LLM provider using Llama models."""

    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or getattr(settings, 'groq_llm_model', self.DEFAULT_MODEL)

        if not self.api_key:
            raise ValueError(
                "Groq API key not provided. "
                "Set GROQ_API_KEY in .env file. "
                "Get FREE key at https://console.groq.com"
            )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate response using Groq API."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Groq API error: {response.status} - {error_text}")
                        raise Exception(f"Groq API error: {response.status} - {error_text}")

                    data = await response.json()

                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    model = data.get("model", self.model)

                    return LLMResponse(
                        content=content,
                        tokens_used=usage.get("total_tokens"),
                        model=model,
                    )

            except aiohttp.ClientError as e:
                logger.error(f"Network error calling Groq: {e}")
                raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream response from Groq API."""
        import json as json_module

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Groq API error: {response.status}")

                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json_module.loads(line[6:])
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json_module.JSONDecodeError, KeyError, IndexError):
                            continue

    @property
    def name(self) -> str:
        return f"groq/{self.model}"
