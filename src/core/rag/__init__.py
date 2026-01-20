"""
RAG Pipeline - orchestrates retrieval and generation.
"""

from dataclasses import dataclass

from src.core.rag.retriever import ProductRetriever, RetrievalResult, get_retriever
from src.core.rag.generator import ResponseGenerator, GenerationResult, get_generator


@dataclass
class RAGResponse:
    """Complete RAG response."""

    answer: str
    products: list[dict]
    confidence_scores: list[float]
    should_escalate: bool
    escalation_reason: str | None


class RAGPipeline:
    """
    Main RAG pipeline combining retrieval and generation.

    Usage:
        rag = RAGPipeline()
        response = await rag.query("Сколько стоит черника?")
        print(response.answer)
    """

    def __init__(
        self,
        retriever: ProductRetriever | None = None,
        generator: ResponseGenerator | None = None,
    ):
        self.retriever = retriever or get_retriever()
        self.generator = generator or get_generator()

    async def query(
        self,
        user_query: str,
        filter_available: bool | None = None,
        category: str | None = None,
    ) -> RAGResponse:
        """
        Process user query through RAG pipeline.

        Args:
            user_query: User's question
            filter_available: Only show available products
            category: Filter by category

        Returns:
            RAGResponse with answer and metadata
        """
        # Step 1: Retrieve relevant products
        retrieval_result = await self.retriever.retrieve(
            query=user_query,
            filter_available=filter_available,
            category=category,
        )

        # Step 2: Check confidence
        is_confident = self.retriever.is_confident(retrieval_result)

        # Step 3: Generate response
        generation_result = await self.generator.generate(
            query=user_query,
            retrieval_result=retrieval_result,
            confident=is_confident,
        )

        return RAGResponse(
            answer=generation_result.response,
            products=retrieval_result.products,
            confidence_scores=retrieval_result.scores,
            should_escalate=generation_result.should_escalate,
            escalation_reason=generation_result.escalation_reason,
        )


# Singleton instance
_pipeline: RAGPipeline | None = None


def get_rag_pipeline() -> RAGPipeline:
    """Get RAG pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


async def query(user_query: str, **kwargs) -> RAGResponse:
    """Convenience function to query RAG pipeline."""
    pipeline = get_rag_pipeline()
    return await pipeline.query(user_query, **kwargs)
