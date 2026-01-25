"""
Inline keyboards for order flow.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.core.orders.models import Order


def get_start_order_keyboard() -> InlineKeyboardMarkup:
    """Keyboard to start order process."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, оформить заказ", callback_data="order:start"),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить ещё товары", callback_data="order:add_more"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="order:cancel"),
    )
    return builder.as_markup()


def get_items_confirmation_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Keyboard for items confirmation."""
    builder = InlineKeyboardBuilder()
    
    # Edit buttons for each item
    for i, item in enumerate(order.items):
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {item.product_name[:20]}...", 
                callback_data=f"order:edit_item:{i}"
            ),
            InlineKeyboardButton(
                text="🗑️", 
                callback_data=f"order:delete_item:{i}"
            ),
        )
    
    builder.row(
        InlineKeyboardButton(text="➕ Добавить товар", callback_data="order:add_item"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Продолжить", callback_data="order:confirm_items"),
        InlineKeyboardButton(text="❌ Отменить заказ", callback_data="order:cancel"),
    )
    return builder.as_markup()


def get_edit_item_keyboard(item_index: int) -> InlineKeyboardMarkup:
    """Keyboard for editing single item."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📝 Изменить количество", 
            callback_data=f"order:change_qty:{item_index}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑️ Удалить", 
            callback_data=f"order:delete_item:{item_index}"
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="order:back_to_items"),
    )
    return builder.as_markup()


def get_delete_confirmation_keyboard(item_index: int) -> InlineKeyboardMarkup:
    """Keyboard for delete confirmation."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, удалить", 
            callback_data=f"order:confirm_delete:{item_index}"
        ),
        InlineKeyboardButton(
            text="❌ Нет, оставить", 
            callback_data="order:back_to_items"
        ),
    )
    return builder.as_markup()


def get_delivery_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for delivery type selection."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚚 Доставка", callback_data="order:delivery:delivery"),
    )
    builder.row(
        InlineKeyboardButton(text="🏪 Самовывоз", callback_data="order:delivery:pickup"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="order:back_to_items"),
    )
    return builder.as_markup()


def get_date_quick_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with quick date options."""
    from datetime import date, timedelta
    
    builder = InlineKeyboardBuilder()
    today = date.today()
    
    # Tomorrow
    tomorrow = today + timedelta(days=1)
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][tomorrow.weekday()]
    builder.row(
        InlineKeyboardButton(
            text=f"📅 Завтра ({tomorrow.strftime('%d.%m')}, {weekday})", 
            callback_data=f"order:date:{tomorrow.isoformat()}"
        ),
    )
    
    # Day after tomorrow
    day_after = today + timedelta(days=2)
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day_after.weekday()]
    builder.row(
        InlineKeyboardButton(
            text=f"📅 Послезавтра ({day_after.strftime('%d.%m')}, {weekday})", 
            callback_data=f"order:date:{day_after.isoformat()}"
        ),
    )
    
    # Next available weekday (skip weekends)
    next_day = today + timedelta(days=3)
    while next_day.weekday() >= 5:  # Skip Sat/Sun
        next_day += timedelta(days=1)
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][next_day.weekday()]
    builder.row(
        InlineKeyboardButton(
            text=f"📅 {next_day.strftime('%d.%m')} ({weekday})", 
            callback_data=f"order:date:{next_day.isoformat()}"
        ),
    )
    
    builder.row(
        InlineKeyboardButton(text="📝 Другая дата", callback_data="order:date:custom"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="order:back_to_delivery"),
    )
    return builder.as_markup()


def get_time_quick_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with quick time options."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌅 Утро (8:00-12:00)", callback_data="order:time:08:00-12:00"),
    )
    builder.row(
        InlineKeyboardButton(text="☀️ День (12:00-16:00)", callback_data="order:time:12:00-16:00"),
    )
    builder.row(
        InlineKeyboardButton(text="🌆 Вечер (16:00-18:00)", callback_data="order:time:16:00-18:00"),
    )
    builder.row(
        InlineKeyboardButton(text="🕐 Любое время", callback_data="order:time:08:00-18:00"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Другое время", callback_data="order:time:custom"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="order:back_to_date"),
    )
    return builder.as_markup()


def get_weekend_warning_keyboard(selected_date: str) -> InlineKeyboardMarkup:
    """Keyboard for weekend warning."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, подтверждаю", 
            callback_data=f"order:date_confirm:{selected_date}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 Выбрать другую дату", 
            callback_data="order:back_to_date"
        ),
    )
    return builder.as_markup()


def get_skip_keyboard(field: str) -> InlineKeyboardMarkup:
    """Keyboard with skip option."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"order:skip:{field}"),
    )
    return builder.as_markup()


def get_use_saved_keyboard(field: str, saved_value: str) -> InlineKeyboardMarkup:
    """Keyboard to use saved value."""
    display_value = saved_value[:30] + "..." if len(saved_value) > 30 else saved_value
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"📋 {display_value}", 
            callback_data=f"order:use_saved:{field}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📝 Ввести новое", 
            callback_data=f"order:enter_new:{field}"
        ),
    )
    return builder.as_markup()


def get_final_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for final order confirmation."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="order:submit"),
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Товары", callback_data="order:edit:items"),
        InlineKeyboardButton(text="📍 Доставка", callback_data="order:edit:delivery"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 Контакты", callback_data="order:edit:contact"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data="order:edit:comment"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отменить заказ", callback_data="order:cancel"),
    )
    return builder.as_markup()


def get_cancel_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for cancel confirmation."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, отменить", callback_data="order:confirm_cancel"),
        InlineKeyboardButton(text="❌ Нет, продолжить", callback_data="order:continue"),
    )
    return builder.as_markup()


def get_order_submitted_keyboard() -> InlineKeyboardMarkup:
    """Keyboard after order submitted."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Новый заказ", callback_data="order:new"),
    )
    builder.row(
        InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact:manager"),
    )
    return builder.as_markup()
