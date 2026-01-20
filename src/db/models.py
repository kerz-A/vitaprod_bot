"""
SQLAlchemy models for VitaProd Bot.
Designed for future scalability: price history, customer tracking, preferences.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# =============================================================================
# PRODUCT & PRICE MODELS
# =============================================================================


class Category(Base):
    """Product category (e.g., 'ЯГОДЫ ЗАМОРОЖЕННЫЕ', 'ОВОЩИ ЗАМОРОЖЕННЫЕ')."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    products: Mapped[list["Product"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}')>"


class Product(Base):
    """Product in the catalog."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    # Current state (denormalized for fast access)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    unit: Mapped[str] = mapped_column(String(50), default="кг")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    category: Mapped["Category"] = relationship(back_populates="products")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="product", order_by="desc(PriceHistory.date)"
    )

    # Indexes
    __table_args__ = (
        UniqueConstraint("name", "category_id", name="uq_product_name_category"),
        Index("ix_products_name", "name"),
        Index("ix_products_available", "is_available"),
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', price={self.current_price})>"


class PriceHistory(Base):
    """Historical price records for tracking changes."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)

    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Change tracking
    previous_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="price_history")

    # Indexes
    __table_args__ = (
        Index("ix_price_history_product_date", "product_id", "date"),
        Index("ix_price_history_date", "date"),
    )

    def __repr__(self) -> str:
        return f"<PriceHistory(product_id={self.product_id}, price={self.price}, date={self.date})>"


class PriceList(Base):
    """Metadata about uploaded price lists."""

    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    products_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PriceList(id={self.id}, date={self.date}, products={self.products_count})>"


# =============================================================================
# CUSTOMER MODELS (for future use)
# =============================================================================


class Customer(Base):
    """Customer/Lead profile."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Profile
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Classification
    customer_type: Mapped[str] = mapped_column(
        String(50), default="lead"
    )  # lead, regular, vip
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Settings
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    interests: Mapped[list["CustomerInterest"]] = relationship(back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, telegram_id={self.telegram_id})>"


class CustomerInterest(Base):
    """Products customer is interested in (for notifications)."""

    __tablename__ = "customer_interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)

    # Interest type
    interest_type: Mapped[str] = mapped_column(
        String(50), default="notify_available"
    )  # notify_available, regular_order, one_time

    # For "don't remind me" feature
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_after: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="interests")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        UniqueConstraint("customer_id", "product_id", name="uq_customer_product_interest"),
    )

    def __repr__(self) -> str:
        return f"<CustomerInterest(customer={self.customer_id}, product={self.product_id})>"


# =============================================================================
# CONVERSATION TRACKING (for context and analytics)
# =============================================================================


class Conversation(Base):
    """Conversation session with a customer."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Outcome
    was_escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, customer={self.customer_id})>"


class Message(Base):
    """Individual message in a conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # RAG metadata
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retrieved_products: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON list of product IDs

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conversation", "conversation_id"),)

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role='{self.role}')>"
