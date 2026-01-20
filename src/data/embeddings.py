"""
Embedding service using sentence-transformers.
Runs locally, no API costs.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import settings


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(
        self,
        texts: str | list[str],
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Generate embeddings for texts.

        Args:
            texts: Single text or list of texts
            normalize: Whether to L2-normalize vectors

        Returns:
            Numpy array of shape (n_texts, embedding_dim)
        """
        if isinstance(texts, str):
            texts = [texts]

        # Add instruction prefix for E5 models
        if "e5" in self.model_name.lower():
            texts = [f"query: {t}" for t in texts]

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )

        return embeddings

    def encode_query(self, query: str) -> list[float]:
        """Encode a single query and return as list."""
        embedding = self.encode(query)
        return embedding[0].tolist()

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Get cached embedding service instance."""
    return EmbeddingService()
