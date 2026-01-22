"""
Message handler - main conversation handler using LangGraph.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message

from src.core.graph import chat

router = Router(name="price_query")
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_message(message: Message) -> None:
    """
    Handle user messages using LangGraph conversation flow.
    Maintains conversation memory per user.
    """
    user_query = message.text.strip()

    if not user_query:
        return

    # Get user info
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username

    # Show typing indicator
    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing",
    )

    try:
        # Process through LangGraph (with memory)
        response = await chat(
            user_id=user_id,
            message=user_query,
            user_name=user_name,
        )

        # Send response
        await message.answer(response)

        logger.info(
            f"User {user_id} ({user_name}): {user_query[:50]}..."
        )

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)

        await message.answer(
            "Извините, произошла ошибка при обработке запроса. "
            "Пожалуйста, попробуйте позже или свяжитесь с менеджером:\n"
            "📞 +7 912 828-18-38"
        )
