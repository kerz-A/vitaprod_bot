"""
Start command handler.
"""

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from src.core.graph import clear_conversation

router = Router(name="start")


# Клавиатура с основными действиями
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Весь ассортимент в наличии")],
        [KeyboardButton(text="💰 Узнать цену товара")],
        [KeyboardButton(text="📞 Связаться с менеджером")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Введите название товара или выберите действие"
)


WELCOME_MESSAGE = """👋 Добро пожаловать в <b>ВитаПрод</b>!

Мы предлагаем оптовые поставки замороженных ягод, овощей, фруктов и грибов.

<b>🔹 Что я умею:</b>
• Показать весь ассортимент в наличии
• Уточнить актуальную цену на продукцию
• Подсказать похожие товары

<b>🔹 Как пользоваться:</b>
Просто напишите название товара или выберите действие из меню ниже.

<b>Примеры запросов:</b>
— «Сколько стоит черника?»
— «Что есть из ягод?»
— «Покажи похожие на клубнику»

📍 <b>Адрес:</b> г. Киров, пер. Энгельса, 2
📞 <b>Телефон:</b> +7 912 828-18-38"""


CATALOG_MESSAGE = """📋 <b>Товары в наличии:</b>

Чтобы узнать цену, просто напишите название товара.
Например: «цена на чернику» или «сколько стоит клубника?»"""


PRICE_HELP_MESSAGE = """💰 <b>Как узнать цену:</b>

Просто напишите название интересующего товара.

<b>Примеры:</b>
— «Черника»
— «Сколько стоит малина?»
— «Цена на смородину»

Я найду товар и покажу актуальную цену. Если найдётся несколько похожих — предложу варианты."""


CONTACT_MESSAGE = """📞 <b>Свяжитесь с нами:</b>

📱 Телефон: +7 912 828-18-38
📱 WhatsApp: +7 912 828-18-38
📧 Email: vitaprod43@mail.ru

📍 Адрес: г. Киров, пер. Энгельса, 2

Менеджер ответит на все ваши вопросы по ассортименту, ценам и доставке."""


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(WELCOME_MESSAGE, reply_markup=main_keyboard)


@router.message(Command("catalog"))
async def handle_catalog_command(message: Message) -> None:
    """Handle /catalog command."""
    await show_catalog(message)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(PRICE_HELP_MESSAGE)


@router.message(lambda m: m.text == "📋 Весь ассортимент в наличии")
async def show_catalog(message: Message) -> None:
    """Show all available products."""
    from src.db.vector import vector_db
    
    try:
        # Получаем все товары из Qdrant
        all_points = vector_db.client.scroll(
            collection_name=vector_db.collection_name,
            limit=100,
            with_payload=True,
        )[0]
        
        # Группируем по категориям и форме
        categories = {}
        for point in all_points:
            payload = point.payload
            if payload.get("is_available", False):
                category = payload.get("category", "Другое")
                product_form = payload.get("product_form", "")
                
                # Создаём ключ "Категория (форма)"
                if product_form:
                    group_key = f"{category} ({product_form.lower()})"
                else:
                    group_key = category
                
                if group_key not in categories:
                    categories[group_key] = []
                
                name = payload.get("name", "")
                price = payload.get("price")
                origin = payload.get("origin_country", "")
                
                # Формируем строку товара
                name_with_origin = f"{name} ({origin})" if origin else name
                price_str = f"{price:.0f} ₽/кг" if price else "цена уточняется"
                categories[group_key].append(f"• {name_with_origin} — {price_str}")
        
        if not categories:
            await message.answer("😔 К сожалению, сейчас нет товаров в наличии.")
            return
        
        # Формируем сообщение
        response = "📋 <b>Товары в наличии:</b>\n\n"
        for category, products in sorted(categories.items()):
            response += f"<b>{category}:</b>\n"
            response += "\n".join(sorted(products))
            response += "\n\n"
        
        response += "💡 <i>Напишите название товара, чтобы узнать подробнее</i>"
        
        await message.answer(response)
        
    except Exception as e:
        await message.answer("😔 Не удалось загрузить каталог. Попробуйте позже.")


@router.message(lambda m: m.text == "💰 Узнать цену товара")
async def show_price_help(message: Message) -> None:
    """Show help for price queries."""
    await message.answer(PRICE_HELP_MESSAGE)


@router.message(lambda m: m.text == "📞 Связаться с менеджером")
async def show_contacts(message: Message) -> None:
    """Show contact information."""
    await message.answer(CONTACT_MESSAGE)


@router.message(Command("clear"))
async def handle_clear(message: Message) -> None:
    """Clear conversation history."""
    user_id = message.from_user.id
    await clear_conversation(user_id)
    await message.answer(
        "🔄 История диалога очищена. Начнём сначала!\n\n"
        "Чем могу помочь?",
        reply_markup=main_keyboard
    )

