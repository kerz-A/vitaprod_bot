"""
Configuration management for VitaProd Bot.
Loads settings from environment variables with validation.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    data_dir: Path = Path(__file__).parent.parent / "data"

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")

    # LLM Provider
    llm_provider: Literal["gigachat", "yandexgpt"] = Field(
        default="gigachat", description="LLM provider to use"
    )

    # GigaChat
    gigachat_credentials: Optional[str] = Field(
        default=None, description="GigaChat API credentials"
    )
    gigachat_scope: str = Field(
        default="GIGACHAT_API_PERS", description="GigaChat API scope"
    )

    # YandexGPT
    yandex_api_key: Optional[str] = Field(default=None, description="Yandex API key")
    yandex_folder_id: Optional[str] = Field(default=None, description="Yandex folder ID")

    # Qdrant
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_collection_name: str = Field(
        default="vitaprod_products", description="Qdrant collection name"
    )

    # Database
    database_url: Optional[str] = Field(
        default=None,
        description="Database connection URL",
    )
    
    # PostgreSQL for LangGraph conversations
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5433, description="PostgreSQL port")
    postgres_user: str = Field(default="vitaprod", description="PostgreSQL user")
    postgres_password: str = Field(default="vitaprod_secret", description="PostgreSQL password")
    postgres_db: str = Field(default="vitaprod", description="PostgreSQL database")
    
    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL for LangGraph."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def async_postgres_url(self) -> str:
        """Get async PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def db_url(self) -> str:
        """Get database URL with absolute path."""
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.data_dir / 'vitaprod.db'}"

    # Escalation contacts
    escalation_phone: str = Field(
        default="+7 912 828-18-38", description="Phone for escalation"
    )
    escalation_whatsapp: str = Field(
        default="+7 912 828-18-38", description="WhatsApp for escalation"
    )
    escalation_email: str = Field(
        default="vitaprod43@mail.ru", description="Email for escalation"
    )
    
    # Manager notification
    manager_telegram_id: Optional[int] = Field(
        default=None, description="Telegram ID of manager to receive orders"
    )

    # Embeddings
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-small",
        description="Sentence transformers model for embeddings",
    )
    embedding_dimension: int = Field(
        default=384, description="Embedding vector dimension"
    )

    # RAG settings
    confidence_threshold: float = Field(
        default=0.7, description="Confidence threshold for escalation"
    )
    top_k_results: int = Field(
        default=5, description="Number of results to retrieve from vector DB"
    )

    # Debug
    debug: bool = Field(default=False, description="Debug mode")

    @property
    def prices_dir(self) -> Path:
        """Directory for price list files."""
        return self.data_dir / "prices"

    @property
    def sqlite_path(self) -> Path:
        """Path to SQLite database file."""
        return self.data_dir / "vitaprod.db"


# Global settings instance
settings = Settings()
