"""
Retriever - searches for relevant products in vector database.
"""

from dataclasses import dataclass

from src.config import settings
from src.data.embeddings import get_embedding_service
from src.db.vector import vector_db


@dataclass
class RetrievalResult:
    """Result of product retrieval."""

    products: list[dict]
    scores: list[float]
    query: str


class ProductRetriever:
    """Retrieves relevant products based on user query."""

    def __init__(self):
        self.embedding_service = get_embedding_service()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filter_available: bool | None = None,
        category: str | None = None,
    ) -> RetrievalResult:
        """
        Search for products matching the query.

        Args:
            query: User's search query
            top_k: Number of results to return
            filter_available: Filter by availability
            category: Filter by category

        Returns:
            RetrievalResult with matching products
        """
        top_k = top_k or settings.top_k_results

        # Generate query embedding
        query_vector = self.embedding_service.encode_query(query)

        # Search in vector DB
        results = vector_db.search(
            query_vector=query_vector,
            limit=top_k,
            filter_available=filter_available,
            category=category,
        )

        products = [r["payload"] for r in results]
        scores = [r["score"] for r in results]

        return RetrievalResult(
            products=products,
            scores=scores,
            query=query,
        )

    def is_confident(self, result: RetrievalResult) -> bool:
        """
        Check if retrieval results are confident enough.

        Returns True if we have high-confidence results,
        False if we should escalate to human.
        """
        if not result.scores:
            return False

        # Check if top result has good score
        top_score = result.scores[0]
        return top_score >= settings.confidence_threshold


def get_retriever() -> ProductRetriever:
    """Get retriever instance."""
    return ProductRetriever()
