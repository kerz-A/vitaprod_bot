"""
Qdrant vector database client for semantic search.
"""

from typing import Optional

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.config import settings


class VectorDB:
    """Qdrant vector database manager."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
    ):
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection_name = collection_name or settings.qdrant_collection_name
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    async def init_collection(
        self,
        vector_size: int | None = None,
        recreate: bool = False,
    ) -> None:
        """Initialize collection for product embeddings."""
        vector_size = vector_size or settings.embedding_dimension

        if recreate:
            try:
                self.client.delete_collection(self.collection_name)
            except UnexpectedResponse:
                pass  # Collection doesn't exist

        try:
            self.client.get_collection(self.collection_name)
        except UnexpectedResponse:
            # Collection doesn't exist, create it
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

            # Create payload indexes for filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="category",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="is_available",
                field_schema=models.PayloadSchemaType.BOOL,
            )

    def upsert_products(
        self,
        ids: list[int],
        vectors: list[list[float]],
        payloads: list[dict],
    ) -> None:
        """Insert or update product vectors."""
        points = [
            models.PointStruct(id=id_, vector=vector, payload=payload)
            for id_, vector, payload in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(
        self,
        query_vector: list[float],
        limit: int | None = None,
        filter_available: bool | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """
        Search for similar products.

        Args:
            query_vector: Query embedding vector
            limit: Number of results to return
            filter_available: Filter by availability (True/False/None for all)
            category: Filter by category name

        Returns:
            List of search results with scores and payloads
        """
        limit = limit or settings.top_k_results

        # Build filter conditions
        conditions = []
        if filter_available is not None:
            conditions.append(
                models.FieldCondition(
                    key="is_available",
                    match=models.MatchValue(value=filter_available),
                )
            )
        if category:
            conditions.append(
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value=category),
                )
            )

        query_filter = models.Filter(must=conditions) if conditions else None

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    def delete_all(self) -> None:
        """Delete all vectors from collection."""
        try:
            self.client.delete_collection(self.collection_name)
        except UnexpectedResponse:
            pass

    def close(self) -> None:
        """Close client connection."""
        if self._client:
            self._client.close()
            self._client = None


# Global vector DB instance
vector_db = VectorDB()
