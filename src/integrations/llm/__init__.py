"""
LLM provider factory and initialization.
"""

from functools import lru_cache

from src.config import settings
from src.integrations.llm.base import BaseLLM, LLMResponse
from src.integrations.llm.gigachat import GigaChatLLM


def get_llm_provider(provider: str | None = None) -> BaseLLM:
    """
    Get LLM provider instance.

    Args:
        provider: Provider name ('gigachat', 'yandexgpt')
                  If None, uses settings.llm_provider

    Returns:
        LLM provider instance
    """
    provider = provider or settings.llm_provider

    if provider == "gigachat":
        return GigaChatLLM()
    elif provider == "yandexgpt":
        # TODO: Implement YandexGPT when needed
        raise NotImplementedError("YandexGPT not implemented yet")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


@lru_cache(maxsize=1)
def get_default_llm() -> BaseLLM:
    """Get cached default LLM provider."""
    return get_llm_provider()


__all__ = [
    "BaseLLM",
    "LLMResponse",
    "GigaChatLLM",
    "get_llm_provider",
    "get_default_llm",
]
