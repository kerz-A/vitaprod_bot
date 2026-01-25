"""
FSM states for order collection.
"""

from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """States for order collection flow."""
    
    # Сбор товаров
    collecting_items = State()       # Добавление товаров в заказ
    editing_item = State()           # Редактирование позиции
    confirming_items = State()       # Подтверждение списка товаров
    
    # Тип доставки
    selecting_delivery_type = State()  # Выбор: доставка или самовывоз
    
    # Данные доставки
    entering_address = State()       # Ввод адреса доставки
    entering_date = State()          # Ввод желаемой даты
    entering_time = State()          # Ввод желаемого времени
    
    # Данные заказчика
    entering_name = State()          # Ввод имени
    entering_phone = State()         # Ввод телефона
    entering_company = State()       # Ввод компании (опционально)
    
    # Комментарий
    entering_comment = State()       # Ввод комментария (опционально)
    
    # Финальное подтверждение
    final_confirmation = State()     # Итоговое подтверждение заказа
    
    # Редактирование
    editing_order = State()          # Режим редактирования (выбор что редактировать)
