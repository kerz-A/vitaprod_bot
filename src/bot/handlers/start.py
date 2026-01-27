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
        [KeyboardButton(text="📋 Весь ассортимент")],
        [KeyboardButton(text="📞 Связаться с менеджером")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Напишите что вас интересует..."
)


WELCOME_MESSAGE = """👋 <b>Здравствуйте!</b>

С вами <b>Себастьян Перейра</b> — консультант компании «ВитаПрод».

Мы занимаемся оптовыми поставками замороженных и сушёных ягод, овощей, фруктов, грибов и орехов.

<b>Как со мной общаться:</b>
• Спросите о товаре: «Есть черника?»
• Узнайте цену: «Сколько стоит малина?»
• Закажите: «Хочу чернику 10 кг»

<b>🔘 Кнопки внизу экрана:</b>
• «📋 Весь ассортимент» — покажу все товары в наличии
• «📞 Связаться с менеджером» — контакты для связи

<b>Команды:</b>
/help — справка по работе с ботом
/clear — начать диалог заново

💡 <i>Совет: сначала уточните наличие товара, а потом оформляйте заказ — так будет удобнее!</i>"""


CONTACT_MESSAGE = """📞 <b>Свяжитесь с нами:</b>

📱 Телефон: +7 912 828-18-38
📱 WhatsApp: +7 912 828-18-38
📧 Email: vitaprod43@mail.ru

📍 Адрес: г. Киров, пер. Энгельса, 2

Менеджер ответит на все ваши вопросы по ассортименту, ценам и доставке."""


HELP_MESSAGE = """🤖 <b>Как я могу помочь:</b>

<b>Узнать о товарах:</b>
• Напишите название — покажу цену и наличие
• Спросите о категории — «что есть из ягод?»
• Нажмите «📋 Весь ассортимент» — покажу все товары

<b>Оформить заказ:</b>
• Напишите «хочу чернику 10 кг» — начну оформление
• Или выберите товары и скажите «оформить»

<b>🔘 Кнопки внизу экрана:</b>
• «📋 Весь ассортимент» — все товары в наличии
• «📞 Связаться с менеджером» — контакты

<b>Команды:</b>
/clear — очистить историю диалога
/help — эта справка

💡 Я запоминаю наш диалог, так что можете уточнять: «а в каком виде?», «а цена?»"""


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(WELCOME_MESSAGE, reply_markup=main_keyboard)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(HELP_MESSAGE, reply_markup=main_keyboard)


@router.message(lambda m: m.text in ["📋 Весь ассортимент", "📋 Весь ассортимент в наличии"])
async def show_catalog(message: Message) -> None:
    """Show all available products."""
    from src.db.vector import vector_db
    
    try:
        # Получаем все товары из Qdrant
        all_points = vector_db.client.scroll(
            collection_name=vector_db.collection_name,
            limit=200,
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
        
        response += "💡 <i>Напишите название товара, чтобы узнать подробнее или заказать</i>"
        
        await message.answer(response)
        
    except Exception as e:
        await message.answer("😔 Не удалось загрузить каталог. Попробуйте позже.")


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