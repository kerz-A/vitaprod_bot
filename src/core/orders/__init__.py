"""
Orders module for VitaProd bot.
Handles order collection, validation, and export.
"""

from src.core.orders.models import (
    Order,
    OrderItem,
    OrderStatus,
    CustomerInfo,
    DeliveryInfo,
    DeliveryType,
    PackagingInfo,
    PackagingType,
)
from src.core.orders.states import OrderStates
from src.core.orders.validators import (
    PhoneValidator,
    DateValidator,
    TimeValidator,
    AddressValidator,
    QuantityValidator,
)
from src.core.orders.exporter import order_exporter
from src.core.orders.intent import detect_order_intent, quick_order_check, format_order_suggestion

__all__ = [
    # Models
    "Order",
    "OrderItem",
    "OrderStatus",
    "CustomerInfo",
    "DeliveryInfo",
    "DeliveryType",
    "PackagingInfo",
    "PackagingType",
    # States
    "OrderStates",
    # Validators
    "PhoneValidator",
    "DateValidator",
    "TimeValidator",
    "AddressValidator",
    "QuantityValidator",
    # Exporter
    "order_exporter",
    # Intent
    "detect_order_intent",
    "quick_order_check",
    "format_order_suggestion",
]