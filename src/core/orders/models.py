"""
Order models for VitaProd bot.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import Optional
import uuid


class OrderStatus(Enum):
    """Order status enum."""
    DRAFT = "draft"              # Сбор данных
    PENDING = "pending"          # Ожидает подтверждения клиента
    CONFIRMED = "confirmed"      # Подтверждён клиентом
    SENT = "sent"               # Отправлен менеджеру
    PROCESSING = "processing"    # В работе у менеджера
    COMPLETED = "completed"      # Выполнен
    CANCELLED = "cancelled"      # Отменён


class DeliveryType(Enum):
    """Delivery type enum."""
    DELIVERY = "delivery"        # Доставка
    PICKUP = "pickup"           # Самовывоз


class PackagingType(Enum):
    """Packaging type enum."""
    BOX = "box"                 # Коробка
    BAG = "bag"                 # Мешок
    ANY = "any"                 # Любая (на усмотрение склада)


@dataclass
class OrderItem:
    """Single item in order."""
    product_name: str
    category: str
    product_form: str           # Замороженные/Сушёные
    quantity_kg: float
    price_per_kg: float
    origin_country: Optional[str] = None
    
    @property
    def total_price(self) -> float:
        """Calculate total price for this item."""
        return self.quantity_kg * self.price_per_kg
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "product_name": self.product_name,
            "category": self.category,
            "product_form": self.product_form,
            "quantity_kg": self.quantity_kg,
            "price_per_kg": self.price_per_kg,
            "total_price": self.total_price,
            "origin_country": self.origin_country,
        }


@dataclass
class PackagingInfo:
    """Packaging information."""
    packaging_type: PackagingType = PackagingType.ANY
    weight_per_unit: Optional[float] = None  # кг в одном тарном месте
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "packaging_type": self.packaging_type.value,
            "weight_per_unit": self.weight_per_unit,
        }
    
    def format_summary(self) -> str:
        """Format packaging as text."""
        type_names = {
            PackagingType.BOX: "Коробка",
            PackagingType.BAG: "Мешок",
            PackagingType.ANY: "Любая",
        }
        result = type_names.get(self.packaging_type, "Любая")
        if self.weight_per_unit:
            result += f" по {self.weight_per_unit:.0f} кг"
        return result


@dataclass
class CustomerInfo:
    """Customer information."""
    telegram_id: int
    telegram_username: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "telegram_id": self.telegram_id,
            "telegram_username": self.telegram_username,
            "name": self.name,
            "phone": self.phone,
            "company": self.company,
        }


@dataclass
class DeliveryInfo:
    """Delivery information."""
    delivery_type: DeliveryType = DeliveryType.DELIVERY
    address: Optional[str] = None
    desired_date: Optional[date] = None
    desired_time_from: Optional[time] = None
    desired_time_to: Optional[time] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "delivery_type": self.delivery_type.value,
            "address": self.address,
            "desired_date": self.desired_date.isoformat() if self.desired_date else None,
            "desired_time_from": self.desired_time_from.isoformat() if self.desired_time_from else None,
            "desired_time_to": self.desired_time_to.isoformat() if self.desired_time_to else None,
        }
    
    def format_time_slot(self) -> str:
        """Format time slot as string."""
        if self.desired_time_from and self.desired_time_to:
            return f"{self.desired_time_from.strftime('%H:%M')} - {self.desired_time_to.strftime('%H:%M')}"
        elif self.desired_time_from:
            return f"с {self.desired_time_from.strftime('%H:%M')}"
        elif self.desired_time_to:
            return f"до {self.desired_time_to.strftime('%H:%M')}"
        return "в течение дня"


@dataclass
class Order:
    """Complete order model."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    created_at: datetime = field(default_factory=datetime.now)
    status: OrderStatus = OrderStatus.DRAFT
    
    items: list[OrderItem] = field(default_factory=list)
    customer: Optional[CustomerInfo] = None
    delivery: Optional[DeliveryInfo] = None
    packaging: Optional[PackagingInfo] = None
    comment: Optional[str] = None
    
    # Metadata
    sent_to_manager_at: Optional[datetime] = None
    manager_notified: bool = False
    
    @property
    def total_quantity(self) -> float:
        """Total quantity in kg."""
        return sum(item.quantity_kg for item in self.items)
    
    @property
    def total_price(self) -> float:
        """Total order price."""
        return sum(item.total_price for item in self.items)
    
    @property
    def order_number(self) -> str:
        """Human-readable order number."""
        return f"#{self.id}"
    
    def add_item(self, item: OrderItem) -> None:
        """Add item to order."""
        # Check if same product already exists
        for existing in self.items:
            if (existing.product_name == item.product_name and 
                existing.product_form == item.product_form):
                # Update quantity
                existing.quantity_kg += item.quantity_kg
                return
        self.items.append(item)
    
    def remove_item(self, index: int) -> bool:
        """Remove item by index."""
        if 0 <= index < len(self.items):
            self.items.pop(index)
            return True
        return False
    
    def update_item_quantity(self, index: int, quantity: float) -> bool:
        """Update item quantity."""
        if 0 <= index < len(self.items) and quantity > 0:
            self.items[index].quantity_kg = quantity
            return True
        return False
    
    def is_complete(self) -> bool:
        """Check if order has all required data."""
        return (
            len(self.items) > 0 and
            self.customer is not None and
            self.customer.phone is not None and
            self.delivery is not None and
            (self.delivery.delivery_type == DeliveryType.PICKUP or 
             self.delivery.address is not None)
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "order_number": self.order_number,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "items": [item.to_dict() for item in self.items],
            "customer": self.customer.to_dict() if self.customer else None,
            "delivery": self.delivery.to_dict() if self.delivery else None,
            "packaging": self.packaging.to_dict() if self.packaging else None,
            "comment": self.comment,
            "total_quantity": self.total_quantity,
            "total_price": self.total_price,
        }
    
    def format_items_summary(self) -> str:
        """Format items as text summary."""
        lines = []
        for i, item in enumerate(self.items, 1):
            origin = f" ({item.origin_country})" if item.origin_country else ""
            lines.append(
                f"{i}. {item.product_name}{origin} ({item.product_form.lower()}) — "
                f"{item.quantity_kg:.0f} кг × {item.price_per_kg:.0f} ₽ = "
                f"{item.total_price:.0f} ₽"
            )
        return "\n".join(lines)
    
    def format_full_summary(self) -> str:
        """Format complete order summary for confirmation."""
        lines = [
            f"📦 <b>Заявка {self.order_number}</b>",
            f"📅 {self.created_at.strftime('%d.%m.%Y %H:%M')}",
            "",
            "<b>Товары:</b>",
            self.format_items_summary(),
            "",
            f"<b>Итого:</b> {self.total_quantity:.0f} кг — {self.total_price:.0f} ₽",
        ]
        
        # Packaging info
        if self.packaging:
            lines.append("")
            lines.append(f"📦 <b>Упаковка:</b> {self.packaging.format_summary()}")
        
        if self.delivery:
            lines.append("")
            if self.delivery.delivery_type == DeliveryType.PICKUP:
                lines.append("🏪 <b>Самовывоз</b>")
                lines.append("📍 г. Киров, пер. Энгельса, 2")
            else:
                lines.append("🚚 <b>Доставка:</b>")
                if self.delivery.address:
                    lines.append(f"📍 {self.delivery.address}")
            
            if self.delivery.desired_date:
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][self.delivery.desired_date.weekday()]
                lines.append(f"📅 {self.delivery.desired_date.strftime('%d.%m.%Y')} ({weekday})")
                lines.append(f"🕐 {self.delivery.format_time_slot()}")
        
        if self.customer:
            lines.append("")
            lines.append("<b>Заказчик:</b>")
            if self.customer.name:
                lines.append(f"👤 {self.customer.name}")
            if self.customer.phone:
                lines.append(f"📞 {self.customer.phone}")
            if self.customer.company:
                lines.append(f"🏢 {self.customer.company}")
        
        if self.comment:
            lines.append("")
            lines.append(f"💬 <b>Комментарий:</b> {self.comment}")
        
        return "\n".join(lines)