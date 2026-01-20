"""
Generator - generates responses using LLM based on retrieved products.
"""

from dataclasses import dataclass

from src.config import settings
from src.core.rag.prompts import build_rag_prompt, build_system_prompt, NO_RESULTS_PROMPT
from src.core.rag.retriever import RetrievalResult
from src.integrations.llm import get_default_llm


@dataclass
class GenerationResult:
    """Result of response generation."""

    response: str
    should_escalate: bool
    escalation_reason: str | None
    products_mentioned: list[dict]


class ResponseGenerator:
    """Generates responses based on retrieved products."""

    def __init__(self):
        self.llm = get_default_llm()

    async def generate(
        self,
        query: str,
        retrieval_result: RetrievalResult,
        confident: bool = True,
    ) -> GenerationResult:
        """
        Generate response for user query.

        Args:
            query: Original user query
            retrieval_result: Products found by retriever
            confident: Whether retrieval was confident

        Returns:
            GenerationResult with response and metadata
        """
        system_prompt = build_system_prompt()

        # Determine if we should escalate
        should_escalate = False
        escalation_reason = None

        if not retrieval_result.products:
            # No products found
            prompt = NO_RESULTS_PROMPT.format(query=query)
            should_escalate = True
            escalation_reason = "no_products_found"
        elif not confident:
            # Low confidence in results
            prompt = build_rag_prompt(query, retrieval_result.products)
            should_escalate = True
            escalation_reason = "low_confidence"
        else:
            # Normal case - good results
            prompt = build_rag_prompt(query, retrieval_result.products)

        # Generate response
        llm_response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=512,
        )

        # Add escalation info if needed
        response_text = llm_response.content

        if should_escalate and "менеджер" not in response_text.lower():
            response_text += self._get_escalation_text()

        return GenerationResult(
            response=response_text,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            products_mentioned=retrieval_result.products,
        )

    def _get_escalation_text(self) -> str:
        """Get escalation contact text."""
        return (
            f"\n\nЕсли нужна дополнительная информация, свяжитесь с менеджером:\n"
            f"📞 {settings.escalation_phone}\n"
            f"💬 WhatsApp: {settings.escalation_whatsapp}"
        )


def get_generator() -> ResponseGenerator:
    """Get generator instance."""
    return ResponseGenerator()
