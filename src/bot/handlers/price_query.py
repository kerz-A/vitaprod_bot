"""
Price query handler - main conversation handler.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message

from src.core.rag import query as rag_query

router = Router(name="price_query")
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_price_query(message: Message) -> None:
    """Handle user questions about products and prices."""
    user_query = message.text.strip()

    if not user_query:
        return

    # Show typing indicator
    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing",
    )

    try:
        # Query RAG pipeline
        response = await rag_query(user_query)

        # Send response
        await message.answer(response.answer)

        # Log for analytics (will be useful for improving the bot)
        logger.info(
            f"Query: {user_query[:50]}... | "
            f"Products: {len(response.products)} | "
            f"Escalated: {response.should_escalate}"
        )

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)

        await message.answer(
            "Извините, произошла ошибка при обработке запроса. "
            "Пожалуйста, попробуйте позже или свяжитесь с менеджером:\n"
            "📞 +7 912 828-18-38"
        )
