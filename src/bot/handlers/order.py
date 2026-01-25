"""
Order handling for VitaProd bot.
Manages the complete order flow using FSM.
"""

import logging
from datetime import datetime, date, time
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from src.core.orders import (
    Order, OrderItem, OrderStatus, CustomerInfo, DeliveryInfo, DeliveryType,
    OrderStates, PhoneValidator, DateValidator, TimeValidator, AddressValidator,
    order_exporter,
)
from src.bot.keyboards.order import (
    get_start_order_keyboard,
    get_items_confirmation_keyboard,
    get_edit_item_keyboard,
    get_delete_confirmation_keyboard,
    get_delivery_type_keyboard,
    get_date_quick_keyboard,
    get_time_quick_keyboard,
    get_weekend_warning_keyboard,
    get_skip_keyboard,
    get_use_saved_keyboard,
    get_final_confirmation_keyboard,
    get_cancel_confirmation_keyboard,
    get_order_submitted_keyboard,
)
from src.config import settings

logger = logging.getLogger(__name__)

router = Router(name="orders")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def get_or_create_order(state: FSMContext) -> Order:
    """Get existing order from state or create new one."""
    data = await state.get_data()
    order_data = data.get("order")
    
    if order_data:
        # Reconstruct Order from dict
        order = Order(
            id=order_data.get("id"),
            created_at=datetime.fromisoformat(order_data["created_at"]),
            status=OrderStatus(order_data.get("status", "draft")),
        )
        
        # Restore items
        for item_data in order_data.get("items", []):
            order.items.append(OrderItem(**{k: v for k, v in item_data.items() if k != "total_price"}))
        
        # Restore customer
        if order_data.get("customer"):
            order.customer = CustomerInfo(**order_data["customer"])
        
        # Restore delivery
        if order_data.get("delivery"):
            del_data = order_data["delivery"]
            order.delivery = DeliveryInfo(
                delivery_type=DeliveryType(del_data["delivery_type"]),
                address=del_data.get("address"),
                desired_date=date.fromisoformat(del_data["desired_date"]) if del_data.get("desired_date") else None,
                desired_time_from=time.fromisoformat(del_data["desired_time_from"]) if del_data.get("desired_time_from") else None,
                desired_time_to=time.fromisoformat(del_data["desired_time_to"]) if del_data.get("desired_time_to") else None,
            )
        
        order.comment = order_data.get("comment")
        return order
    
    return Order()


async def save_order_to_state(state: FSMContext, order: Order) -> None:
    """Save order to FSM state."""
    await state.update_data(order=order.to_dict())


async def get_saved_customer_data(telegram_id: int) -> Optional[dict]:
    """Get saved customer data from database."""
    # TODO: Implement database lookup
    # For now, return None
    return None


async def save_customer_data(customer: CustomerInfo) -> None:
    """Save customer data to database for future autofill."""
    # TODO: Implement database save
    pass


def format_order_progress(current_step: int, total_steps: int = 5) -> str:
    """Format progress indicator."""
    filled = "●" * current_step
    empty = "○" * (total_steps - current_step)
    return f"[{filled}{empty}] Шаг {current_step} из {total_steps}"


# =============================================================================
# ORDER START
# =============================================================================

async def start_order_from_cart(
    message: Message, 
    state: FSMContext, 
    items: list[dict]
) -> None:
    """
    Start order process with items from conversation.
    Called from main chat handler when order intent is detected.
    """
    order = Order()
    
    # Add items to order
    for item_data in items:
        order.add_item(OrderItem(
            product_name=item_data["name"],
            category=item_data.get("category", ""),
            product_form=item_data.get("product_form", "Замороженные"),
            quantity_kg=item_data["quantity"],
            price_per_kg=item_data["price"],
            origin_country=item_data.get("origin_country"),
        ))
    
    # Initialize customer with telegram info
    order.customer = CustomerInfo(
        telegram_id=message.from_user.id,
        telegram_username=message.from_user.username,
        name=message.from_user.full_name,
    )
    
    await save_order_to_state(state, order)
    await state.set_state(OrderStates.confirming_items)
    
    # Show order summary
    text = (
        "📦 <b>Оформление заказа</b>\n\n"
        f"{order.format_items_summary()}\n\n"
        f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽\n\n"
        "Всё верно?"
    )
    
    await message.answer(text, reply_markup=get_items_confirmation_keyboard(order))


@router.callback_query(F.data == "order:start")
async def handle_order_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle order start button."""
    await callback.answer()
    order = await get_or_create_order(state)
    
    if not order.items:
        await callback.message.edit_text(
            "❌ В заказе нет товаров. Сначала выберите товары."
        )
        await state.clear()
        return
    
    await state.set_state(OrderStates.selecting_delivery_type)
    
    text = (
        f"{format_order_progress(1)}\n\n"
        "🚚 <b>Способ получения</b>\n\n"
        "Как вы хотите получить заказ?"
    )
    
    await callback.message.edit_text(text, reply_markup=get_delivery_type_keyboard())


# =============================================================================
# ITEMS MANAGEMENT
# =============================================================================

@router.callback_query(F.data == "order:back_to_items")
async def handle_back_to_items(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to items confirmation."""
    await callback.answer()
    order = await get_or_create_order(state)
    await state.set_state(OrderStates.confirming_items)
    
    text = (
        "📦 <b>Товары в заказе</b>\n\n"
        f"{order.format_items_summary()}\n\n"
        f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽"
    )
    
    await callback.message.edit_text(text, reply_markup=get_items_confirmation_keyboard(order))


@router.callback_query(F.data.startswith("order:edit_item:"))
async def handle_edit_item(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle item edit request."""
    await callback.answer()
    item_index = int(callback.data.split(":")[-1])
    order = await get_or_create_order(state)
    
    if item_index >= len(order.items):
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    item = order.items[item_index]
    await state.update_data(editing_item_index=item_index)
    
    text = (
        f"✏️ <b>Редактирование</b>\n\n"
        f"<b>{item.product_name}</b>\n"
        f"Форма: {item.product_form}\n"
        f"Количество: {item.quantity_kg:.0f} кг\n"
        f"Цена: {item.price_per_kg:.0f} ₽/кг\n"
        f"Сумма: {item.total_price:.0f} ₽\n\n"
        "Что хотите сделать?"
    )
    
    await callback.message.edit_text(text, reply_markup=get_edit_item_keyboard(item_index))


@router.callback_query(F.data.startswith("order:delete_item:"))
async def handle_delete_item_request(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle item delete request."""
    await callback.answer()
    item_index = int(callback.data.split(":")[-1])
    order = await get_or_create_order(state)
    
    if item_index >= len(order.items):
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    item = order.items[item_index]
    
    text = (
        f"🗑️ <b>Удалить товар?</b>\n\n"
        f"{item.product_name} — {item.quantity_kg:.0f} кг\n\n"
        "Это действие нельзя отменить."
    )
    
    await callback.message.edit_text(text, reply_markup=get_delete_confirmation_keyboard(item_index))


@router.callback_query(F.data.startswith("order:confirm_delete:"))
async def handle_confirm_delete(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm item deletion."""
    await callback.answer("Товар удалён")
    item_index = int(callback.data.split(":")[-1])
    order = await get_or_create_order(state)
    
    if order.remove_item(item_index):
        await save_order_to_state(state, order)
    
    if not order.items:
        await callback.message.edit_text(
            "❌ В заказе не осталось товаров. Заказ отменён."
        )
        await state.clear()
        return
    
    # Return to items list
    text = (
        "📦 <b>Товары в заказе</b>\n\n"
        f"{order.format_items_summary()}\n\n"
        f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽"
    )
    
    await callback.message.edit_text(text, reply_markup=get_items_confirmation_keyboard(order))


@router.callback_query(F.data.startswith("order:change_qty:"))
async def handle_change_quantity_request(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle quantity change request."""
    await callback.answer()
    item_index = int(callback.data.split(":")[-1])
    order = await get_or_create_order(state)
    
    if item_index >= len(order.items):
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    item = order.items[item_index]
    await state.set_state(OrderStates.editing_item)
    await state.update_data(editing_item_index=item_index)
    
    text = (
        f"📝 <b>Изменение количества</b>\n\n"
        f"<b>{item.product_name}</b>\n"
        f"Текущее количество: {item.quantity_kg:.0f} кг\n\n"
        "Введите новое количество (в кг):"
    )
    
    await callback.message.edit_text(text)


@router.message(OrderStates.editing_item)
async def handle_quantity_input(message: Message, state: FSMContext) -> None:
    """Handle quantity input for editing."""
    from src.core.orders.validators import QuantityValidator
    
    is_valid, quantity, error = QuantityValidator.validate(message.text)
    
    if not is_valid:
        await message.answer(f"❌ {error}\n\nПопробуйте ещё раз:")
        return
    
    data = await state.get_data()
    item_index = data.get("editing_item_index", 0)
    order = await get_or_create_order(state)
    
    if order.update_item_quantity(item_index, quantity):
        await save_order_to_state(state, order)
        await message.answer("✅ Количество обновлено!")
    
    await state.set_state(OrderStates.confirming_items)
    
    text = (
        "📦 <b>Товары в заказе</b>\n\n"
        f"{order.format_items_summary()}\n\n"
        f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽"
    )
    
    await message.answer(text, reply_markup=get_items_confirmation_keyboard(order))


@router.callback_query(F.data == "order:confirm_items")
async def handle_confirm_items(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm items and proceed to delivery."""
    await callback.answer()
    await state.set_state(OrderStates.selecting_delivery_type)
    
    text = (
        f"{format_order_progress(1)}\n\n"
        "🚚 <b>Способ получения</b>\n\n"
        "Как вы хотите получить заказ?"
    )
    
    await callback.message.edit_text(text, reply_markup=get_delivery_type_keyboard())


# =============================================================================
# DELIVERY TYPE
# =============================================================================

@router.callback_query(F.data == "order:delivery:delivery")
async def handle_delivery_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle delivery selection."""
    await callback.answer()
    order = await get_or_create_order(state)
    
    if not order.delivery:
        order.delivery = DeliveryInfo()
    order.delivery.delivery_type = DeliveryType.DELIVERY
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_address)
    
    # Check for saved address
    saved_data = await get_saved_customer_data(callback.from_user.id)
    
    text = (
        f"{format_order_progress(2)}\n\n"
        "📍 <b>Адрес доставки</b>\n\n"
        "Введите полный адрес:\n"
        "(город, улица, дом, офис/квартира)"
    )
    
    if saved_data and saved_data.get("address"):
        await callback.message.edit_text(
            text, 
            reply_markup=get_use_saved_keyboard("address", saved_data["address"])
        )
    else:
        await callback.message.edit_text(text)


@router.callback_query(F.data == "order:delivery:pickup")
async def handle_pickup_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle pickup selection."""
    await callback.answer()
    order = await get_or_create_order(state)
    
    if not order.delivery:
        order.delivery = DeliveryInfo()
    order.delivery.delivery_type = DeliveryType.PICKUP
    await save_order_to_state(state, order)
    
    # Skip address, go to date
    await state.set_state(OrderStates.entering_date)
    
    text = (
        f"{format_order_progress(2)}\n\n"
        "🏪 <b>Самовывоз</b>\n\n"
        "📍 Адрес склада: г. Киров, пер. Энгельса, 2\n\n"
        "📅 Выберите желаемую дату:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_date_quick_keyboard())


# =============================================================================
# ADDRESS
# =============================================================================

@router.message(OrderStates.entering_address)
async def handle_address_input(message: Message, state: FSMContext) -> None:
    """Handle address input."""
    is_valid, address, error = AddressValidator.validate(message.text)
    
    if not is_valid:
        await message.answer(f"❌ {error}\n\nПопробуйте ещё раз:")
        return
    
    order = await get_or_create_order(state)
    order.delivery.address = address
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_date)
    
    text = (
        f"{format_order_progress(2)}\n\n"
        f"✅ Адрес: {address}\n\n"
        "📅 Выберите желаемую дату доставки:"
    )
    
    await message.answer(text, reply_markup=get_date_quick_keyboard())


# =============================================================================
# DATE
# =============================================================================

@router.callback_query(F.data.startswith("order:date:"))
async def handle_date_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle date selection from quick buttons."""
    await callback.answer()
    date_str = callback.data.split(":")[-1]
    
    if date_str == "custom":
        await state.set_state(OrderStates.entering_date)
        await callback.message.edit_text(
            f"{format_order_progress(2)}\n\n"
            "📅 <b>Введите желаемую дату</b>\n\n"
            "Формат: ДД.ММ.ГГГГ или 'завтра'"
        )
        return
    
    # Parse date
    selected_date = date.fromisoformat(date_str)
    is_weekend = selected_date.weekday() >= 5
    
    if is_weekend:
        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][selected_date.weekday()]
        await callback.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Вы выбрали {selected_date.strftime('%d.%m.%Y')} ({weekday}) — это выходной день.\n\n"
            "В выходные доставка может быть недоступна или ограничена.\n\n"
            "Подтвердить эту дату?",
            reply_markup=get_weekend_warning_keyboard(date_str)
        )
        return
    
    await set_delivery_date(callback, state, selected_date)


@router.callback_query(F.data.startswith("order:date_confirm:"))
async def handle_date_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm date after weekend warning."""
    await callback.answer()
    date_str = callback.data.split(":")[-1]
    selected_date = date.fromisoformat(date_str)
    await set_delivery_date(callback, state, selected_date)


async def set_delivery_date(callback: CallbackQuery, state: FSMContext, selected_date: date) -> None:
    """Set delivery date and proceed to time."""
    order = await get_or_create_order(state)
    order.delivery.desired_date = selected_date
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_time)
    
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][selected_date.weekday()]
    
    text = (
        f"{format_order_progress(2)}\n\n"
        f"✅ Дата: {selected_date.strftime('%d.%m.%Y')} ({weekday})\n\n"
        "🕐 Выберите желаемое время:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_time_quick_keyboard())


@router.message(OrderStates.entering_date)
async def handle_date_input(message: Message, state: FSMContext) -> None:
    """Handle manual date input."""
    is_valid, parsed_date, error, is_weekend = DateValidator.validate(message.text)
    
    if not is_valid:
        await message.answer(f"❌ {error}\n\nПопробуйте ещё раз:")
        return
    
    if is_weekend:
        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][parsed_date.weekday()]
        await message.answer(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Вы выбрали {parsed_date.strftime('%d.%m.%Y')} ({weekday}) — это выходной день.\n\n"
            "В выходные доставка может быть недоступна или ограничена.\n\n"
            "Подтвердить эту дату?",
            reply_markup=get_weekend_warning_keyboard(parsed_date.isoformat())
        )
        return
    
    order = await get_or_create_order(state)
    order.delivery.desired_date = parsed_date
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_time)
    
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][parsed_date.weekday()]
    
    text = (
        f"{format_order_progress(2)}\n\n"
        f"✅ Дата: {parsed_date.strftime('%d.%m.%Y')} ({weekday})\n\n"
        "🕐 Выберите желаемое время:"
    )
    
    await message.answer(text, reply_markup=get_time_quick_keyboard())


# =============================================================================
# TIME
# =============================================================================

@router.callback_query(F.data.startswith("order:time:"))
async def handle_time_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle time selection."""
    await callback.answer()
    time_str = callback.data.split(":", 2)[-1]
    
    if time_str == "custom":
        await state.set_state(OrderStates.entering_time)
        await callback.message.edit_text(
            f"{format_order_progress(2)}\n\n"
            "🕐 <b>Введите желаемое время</b>\n\n"
            "Например: 10:00-14:00 или 'с 10 до 14'"
        )
        return
    
    # Parse time range (e.g., "08:00-12:00")
    time_from_str, time_to_str = time_str.split("-")
    time_from = time.fromisoformat(time_from_str)
    time_to = time.fromisoformat(time_to_str)
    
    await set_delivery_time(callback, state, time_from, time_to)


async def set_delivery_time(
    callback: CallbackQuery, 
    state: FSMContext, 
    time_from: time, 
    time_to: time
) -> None:
    """Set delivery time and proceed to contact info."""
    order = await get_or_create_order(state)
    order.delivery.desired_time_from = time_from
    order.delivery.desired_time_to = time_to
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_name)
    
    # Check for saved name
    saved_name = order.customer.name if order.customer else None
    
    text = (
        f"{format_order_progress(3)}\n\n"
        f"✅ Время: {time_from.strftime('%H:%M')} - {time_to.strftime('%H:%M')}\n\n"
        "👤 <b>Контактные данные</b>\n\n"
        "Как к вам обращаться?"
    )
    
    if saved_name:
        await callback.message.edit_text(
            text,
            reply_markup=get_use_saved_keyboard("name", saved_name)
        )
    else:
        await callback.message.edit_text(text)


@router.message(OrderStates.entering_time)
async def handle_time_input(message: Message, state: FSMContext) -> None:
    """Handle manual time input."""
    is_valid, time_tuple, error = TimeValidator.validate(message.text)
    
    if not is_valid:
        await message.answer(f"❌ {error}\n\nПопробуйте ещё раз:")
        return
    
    time_from, time_to = time_tuple
    
    order = await get_or_create_order(state)
    order.delivery.desired_time_from = time_from
    order.delivery.desired_time_to = time_to
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_name)
    
    text = (
        f"{format_order_progress(3)}\n\n"
        f"✅ Время: {time_from.strftime('%H:%M')} - {time_to.strftime('%H:%M')}\n\n"
        "👤 <b>Контактные данные</b>\n\n"
        "Как к вам обращаться?"
    )
    
    await message.answer(text)


# =============================================================================
# CONTACT INFO
# =============================================================================

@router.callback_query(F.data == "order:use_saved:name")
async def handle_use_saved_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Use saved name."""
    await callback.answer()
    order = await get_or_create_order(state)
    # Name already set from telegram
    await proceed_to_phone(callback.message, state, order, is_callback=True)


@router.callback_query(F.data == "order:enter_new:name")
async def handle_enter_new_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Enter new name instead of saved."""
    await callback.answer()
    await state.set_state(OrderStates.entering_name)
    await callback.message.edit_text(
        f"{format_order_progress(3)}\n\n"
        "👤 <b>Контактные данные</b>\n\n"
        "Введите ваше имя:"
    )


@router.callback_query(F.data == "order:use_saved:phone")
async def handle_use_saved_phone(callback: CallbackQuery, state: FSMContext) -> None:
    """Use saved phone."""
    await callback.answer()
    data = await state.get_data()
    saved_phone = data.get("saved_phone")
    
    if saved_phone:
        order = await get_or_create_order(state)
        order.customer.phone = saved_phone
        await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_company)
    
    text = (
        f"{format_order_progress(3)}\n\n"
        "🏢 <b>Компания</b> (необязательно)\n\n"
        "Введите название компании или нажмите 'Пропустить':"
    )
    
    await callback.message.edit_text(text, reply_markup=get_skip_keyboard("company"))


@router.callback_query(F.data == "order:enter_new:phone")
async def handle_enter_new_phone(callback: CallbackQuery, state: FSMContext) -> None:
    """Enter new phone instead of saved."""
    await callback.answer()
    await state.set_state(OrderStates.entering_phone)
    await callback.message.edit_text(
        f"{format_order_progress(3)}\n\n"
        "📞 <b>Контактный телефон</b>\n\n"
        "Введите номер телефона:"
    )


@router.callback_query(F.data == "order:use_saved:address")
async def handle_use_saved_address(callback: CallbackQuery, state: FSMContext) -> None:
    """Use saved address."""
    await callback.answer()
    data = await state.get_data()
    saved_address = data.get("saved_address")
    
    if saved_address:
        order = await get_or_create_order(state)
        order.delivery.address = saved_address
        await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_date)
    
    text = (
        f"{format_order_progress(2)}\n\n"
        f"✅ Адрес: {saved_address}\n\n"
        "📅 Выберите желаемую дату доставки:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_date_quick_keyboard())


@router.callback_query(F.data == "order:enter_new:address")
async def handle_enter_new_address(callback: CallbackQuery, state: FSMContext) -> None:
    """Enter new address instead of saved."""
    await callback.answer()
    await state.set_state(OrderStates.entering_address)
    await callback.message.edit_text(
        f"{format_order_progress(2)}\n\n"
        "📍 <b>Адрес доставки</b>\n\n"
        "Введите полный адрес:\n"
        "(город, улица, дом, офис/квартира)"
    )


@router.message(OrderStates.entering_name)
async def handle_name_input(message: Message, state: FSMContext) -> None:
    """Handle name input."""
    name = message.text.strip()
    
    if len(name) < 2:
        await message.answer("❌ Имя слишком короткое. Введите ваше имя:")
        return
    
    order = await get_or_create_order(state)
    order.customer.name = name
    await save_order_to_state(state, order)
    
    await proceed_to_phone(message, state, order, is_callback=False)


async def proceed_to_phone(
    message_or_callback, 
    state: FSMContext, 
    order: Order,
    is_callback: bool = False
) -> None:
    """Proceed to phone input."""
    await state.set_state(OrderStates.entering_phone)
    
    saved_data = await get_saved_customer_data(order.customer.telegram_id)
    
    text = (
        f"{format_order_progress(3)}\n\n"
        f"✅ Имя: {order.customer.name}\n\n"
        "📞 <b>Контактный телефон</b>\n\n"
        "Введите номер телефона:"
    )
    
    if is_callback:
        if saved_data and saved_data.get("phone"):
            await message_or_callback.edit_text(
                text,
                reply_markup=get_use_saved_keyboard("phone", saved_data["phone"])
            )
        else:
            await message_or_callback.edit_text(text)
    else:
        if saved_data and saved_data.get("phone"):
            await message_or_callback.answer(
                text,
                reply_markup=get_use_saved_keyboard("phone", saved_data["phone"])
            )
        else:
            await message_or_callback.answer(text)


@router.message(OrderStates.entering_phone)
async def handle_phone_input(message: Message, state: FSMContext) -> None:
    """Handle phone input."""
    is_valid, phone, error = PhoneValidator.validate(message.text)
    
    if not is_valid:
        await message.answer(f"❌ {error}\n\nПопробуйте ещё раз:")
        return
    
    order = await get_or_create_order(state)
    order.customer.phone = phone
    await save_order_to_state(state, order)
    
    await state.set_state(OrderStates.entering_company)
    
    text = (
        f"{format_order_progress(3)}\n\n"
        f"✅ Телефон: {phone}\n\n"
        "🏢 <b>Компания</b> (необязательно)\n\n"
        "Введите название компании или нажмите 'Пропустить':"
    )
    
    await message.answer(text, reply_markup=get_skip_keyboard("company"))


@router.callback_query(F.data == "order:skip:company")
async def handle_skip_company(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip company input."""
    await callback.answer()
    await proceed_to_comment(callback.message, state, is_callback=True)


@router.message(OrderStates.entering_company)
async def handle_company_input(message: Message, state: FSMContext) -> None:
    """Handle company input."""
    order = await get_or_create_order(state)
    order.customer.company = message.text.strip()
    await save_order_to_state(state, order)
    
    await proceed_to_comment(message, state, is_callback=False)


async def proceed_to_comment(message_or_callback, state: FSMContext, is_callback: bool = False) -> None:
    """Proceed to comment input."""
    await state.set_state(OrderStates.entering_comment)
    
    text = (
        f"{format_order_progress(4)}\n\n"
        "💬 <b>Комментарий к заказу</b> (необязательно)\n\n"
        "Укажите дополнительные пожелания или нажмите 'Пропустить':"
    )
    
    if is_callback:
        await message_or_callback.edit_text(text, reply_markup=get_skip_keyboard("comment"))
    else:
        await message_or_callback.answer(text, reply_markup=get_skip_keyboard("comment"))


@router.callback_query(F.data == "order:skip:comment")
async def handle_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip comment input."""
    await callback.answer()
    await show_final_confirmation(callback.message, state, is_callback=True)


@router.message(OrderStates.entering_comment)
async def handle_comment_input(message: Message, state: FSMContext) -> None:
    """Handle comment input."""
    order = await get_or_create_order(state)
    order.comment = message.text.strip()
    await save_order_to_state(state, order)
    
    await show_final_confirmation(message, state, is_callback=False)


# =============================================================================
# FINAL CONFIRMATION
# =============================================================================

async def show_final_confirmation(message_or_callback, state: FSMContext, is_callback: bool = False) -> None:
    """Show final order summary for confirmation."""
    await state.set_state(OrderStates.final_confirmation)
    order = await get_or_create_order(state)
    
    text = (
        f"{format_order_progress(5)}\n\n"
        f"{order.format_full_summary()}\n\n"
        "Проверьте заказ и подтвердите отправку:"
    )
    
    if is_callback:
        await message_or_callback.edit_text(text, reply_markup=get_final_confirmation_keyboard())
    else:
        await message_or_callback.answer(text, reply_markup=get_final_confirmation_keyboard())


@router.callback_query(F.data == "order:submit")
async def handle_order_submit(callback: CallbackQuery, state: FSMContext) -> None:
    """Submit the order."""
    await callback.answer("Отправляем заказ...")
    
    order = await get_or_create_order(state)
    order.status = OrderStatus.SENT
    order.sent_to_manager_at = datetime.now()
    
    # Export to XLSX
    xlsx_path = order_exporter.export(order)
    logger.info(f"Order {order.id} exported to {xlsx_path}")
    
    # Send to manager
    manager_id = settings.manager_telegram_id
    logger.info(f"Manager ID from settings: {manager_id}")
    
    if manager_id:
        try:
            from src.bot.bot import get_bot
            bot = get_bot()
            
            logger.info(f"Sending order {order.id} to manager {manager_id}...")
            
            # Send text notification
            await bot.send_message(
                chat_id=manager_id,
                text=(
                    f"🔔 <b>Новая заявка {order.order_number}</b>\n\n"
                    f"{order.format_full_summary()}"
                ),
                parse_mode="HTML",
            )
            logger.info(f"Text notification sent to {manager_id}")
            
            # Send XLSX file
            await bot.send_document(
                chat_id=manager_id,
                document=FSInputFile(xlsx_path),
                caption=f"📎 Заявка {order.order_number} в формате Excel"
            )
            logger.info(f"XLSX file sent to {manager_id}")
            
            order.manager_notified = True
            logger.info(f"Order {order.id} successfully sent to manager {manager_id}")
            
        except Exception as e:
            logger.error(f"Failed to notify manager {manager_id}: {e}", exc_info=True)
    else:
        logger.warning("MANAGER_TELEGRAM_ID not set in .env!")
    
    # Save customer data for future autofill
    await save_customer_data(order.customer)
    
    # Clear state
    await state.clear()
    
    # Notify customer
    await callback.message.edit_text(
        f"✅ <b>Заявка {order.order_number} принята!</b>\n\n"
        f"Менеджер свяжется с вами в ближайшее время по номеру {order.customer.phone}.\n\n"
        f"📞 Если у вас срочный вопрос: {settings.escalation_phone}",
        reply_markup=get_order_submitted_keyboard()
    )


# =============================================================================
# CANCEL
# =============================================================================

@router.callback_query(F.data == "order:cancel")
async def handle_cancel_request(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel request."""
    await callback.answer()
    await callback.message.edit_text(
        "❌ <b>Отменить заказ?</b>\n\n"
        "Все введённые данные будут потеряны.",
        reply_markup=get_cancel_confirmation_keyboard()
    )


@router.callback_query(F.data == "order:confirm_cancel")
async def handle_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm order cancellation."""
    await callback.answer("Заказ отменён")
    await state.clear()
    await callback.message.edit_text(
        "❌ Заказ отменён.\n\n"
        "Если захотите оформить заказ — просто напишите что вам нужно!"
    )


@router.callback_query(F.data == "order:continue")
async def handle_continue_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Continue order after cancel prompt."""
    await callback.answer()
    await show_final_confirmation(callback.message, state, is_callback=True)


# =============================================================================
# BACK NAVIGATION
# =============================================================================

@router.callback_query(F.data == "order:back_to_delivery")
async def handle_back_to_delivery(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to delivery type selection."""
    await callback.answer()
    await state.set_state(OrderStates.selecting_delivery_type)
    
    text = (
        f"{format_order_progress(1)}\n\n"
        "🚚 <b>Способ получения</b>\n\n"
        "Как вы хотите получить заказ?"
    )
    
    await callback.message.edit_text(text, reply_markup=get_delivery_type_keyboard())


@router.callback_query(F.data == "order:back_to_date")
async def handle_back_to_date(callback: CallbackQuery, state: FSMContext) -> None:
    """Go back to date selection."""
    await callback.answer()
    await state.set_state(OrderStates.entering_date)
    
    order = await get_or_create_order(state)
    
    if order.delivery.delivery_type == DeliveryType.PICKUP:
        text = (
            f"{format_order_progress(2)}\n\n"
            "🏪 <b>Самовывоз</b>\n\n"
            "📍 Адрес склада: г. Киров, пер. Энгельса, 2\n\n"
            "📅 Выберите желаемую дату:"
        )
    else:
        text = (
            f"{format_order_progress(2)}\n\n"
            f"📍 Адрес: {order.delivery.address}\n\n"
            "📅 Выберите желаемую дату доставки:"
        )
    
    await callback.message.edit_text(text, reply_markup=get_date_quick_keyboard())


# =============================================================================
# MISSING HANDLERS - ADD MORE, EDIT, NEW ORDER
# =============================================================================

@router.callback_query(F.data == "order:add_more")
async def handle_add_more(callback: CallbackQuery, state: FSMContext) -> None:
    """User wants to add more items before starting order."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "👍 Хорошо! Напишите какие ещё товары вам нужны.\n\n"
        "Когда будете готовы оформить заказ — просто скажите «оформить заказ»."
    )


@router.callback_query(F.data == "order:add_item")
async def handle_add_item(callback: CallbackQuery, state: FSMContext) -> None:
    """Add another item to order."""
    await callback.answer()
    await state.set_state(OrderStates.collecting_items)
    await callback.message.edit_text(
        "➕ <b>Добавить товар</b>\n\n"
        "Напишите название товара и количество.\n"
        "Например: «черника 20 кг» или «малина 15 кг»\n\n"
        "Или напишите «готово» чтобы продолжить оформление."
    )


@router.message(OrderStates.collecting_items)
async def handle_collecting_items(message: Message, state: FSMContext) -> None:
    """Handle adding items in collecting state."""
    text = message.text.strip().lower()
    
    if text in ["готово", "далее", "продолжить", "хватит"]:
        order = await get_or_create_order(state)
        if not order.items:
            await message.answer("❌ В заказе нет товаров. Добавьте хотя бы один товар.")
            return
        
        await state.set_state(OrderStates.confirming_items)
        text = (
            "📦 <b>Товары в заказе</b>\n\n"
            f"{order.format_items_summary()}\n\n"
            f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽"
        )
        await message.answer(text, reply_markup=get_items_confirmation_keyboard(order))
        return
    
    # Try to parse item from message
    # This is simplified - in production would use LLM
    await message.answer(
        "Для добавления товара используйте формат:\n"
        "«название товара количество кг»\n\n"
        "Или напишите «готово» чтобы продолжить оформление."
    )


@router.callback_query(F.data == "order:edit:items")
async def handle_edit_items(callback: CallbackQuery, state: FSMContext) -> None:
    """Edit items from final confirmation."""
    await callback.answer()
    order = await get_or_create_order(state)
    await state.set_state(OrderStates.confirming_items)
    
    text = (
        "📦 <b>Редактирование товаров</b>\n\n"
        f"{order.format_items_summary()}\n\n"
        f"<b>Итого:</b> {order.total_quantity:.0f} кг — {order.total_price:.0f} ₽"
    )
    
    await callback.message.edit_text(text, reply_markup=get_items_confirmation_keyboard(order))


@router.callback_query(F.data == "order:edit:delivery")
async def handle_edit_delivery(callback: CallbackQuery, state: FSMContext) -> None:
    """Edit delivery from final confirmation."""
    await callback.answer()
    await state.set_state(OrderStates.selecting_delivery_type)
    
    text = (
        "🚚 <b>Изменить способ получения</b>\n\n"
        "Как вы хотите получить заказ?"
    )
    
    await callback.message.edit_text(text, reply_markup=get_delivery_type_keyboard())


@router.callback_query(F.data == "order:edit:contact")
async def handle_edit_contact(callback: CallbackQuery, state: FSMContext) -> None:
    """Edit contact from final confirmation."""
    await callback.answer()
    await state.set_state(OrderStates.entering_name)
    
    text = (
        "👤 <b>Изменить контактные данные</b>\n\n"
        "Как к вам обращаться?"
    )
    
    await callback.message.edit_text(text)


@router.callback_query(F.data == "order:edit:comment")
async def handle_edit_comment(callback: CallbackQuery, state: FSMContext) -> None:
    """Edit comment from final confirmation."""
    await callback.answer()
    await state.set_state(OrderStates.entering_comment)
    
    text = (
        "💬 <b>Изменить комментарий</b>\n\n"
        "Введите комментарий к заказу:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_skip_keyboard("comment"))


@router.callback_query(F.data == "order:new")
async def handle_new_order(callback: CallbackQuery, state: FSMContext) -> None:
    """Start a new order after previous was submitted."""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "📦 <b>Новый заказ</b>\n\n"
        "Напишите какие товары вам нужны.\n"
        "Например: «черника 10 кг и малина 5 кг»"
    )


@router.callback_query(F.data == "contact:manager")
async def handle_contact_manager(callback: CallbackQuery, state: FSMContext) -> None:
    """Show manager contact info."""
    await callback.answer()
    from src.config import settings
    
    await callback.message.answer(
        "📞 <b>Свяжитесь с нами:</b>\n\n"
        f"📱 Телефон: {settings.escalation_phone}\n"
        f"📱 WhatsApp: {settings.escalation_whatsapp}\n"
        f"📧 Email: {settings.escalation_email}\n\n"
        "📍 Адрес: г. Киров, пер. Энгельса, 2"
    )