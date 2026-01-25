"""
Message handler - main conversation handler using LangGraph.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from src.core.graph import chat
from src.core.orders.states import OrderStates
from src.core.orders.intent import detect_order_intent, format_order_suggestion, quick_order_check
from src.bot.keyboards.order import get_start_order_keyboard

router = Router(name="price_query")
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_message(message: Message, state: FSMContext) -> None:
    """
    Handle user messages using LangGraph conversation flow.
    Maintains conversation memory per user.
    Detects order intent and starts order flow when appropriate.
    """
    user_query = message.text.strip()

    if not user_query:
        return
    
    # Check if user is in order FSM state - skip regular processing
    current_state = await state.get_state()
    if current_state and current_state.startswith("OrderStates:"):
        # Let order handlers process this
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
        # Check for order intent (quick check first)
        if quick_order_check(user_query):
            # Get conversation context for intent detection
            from src.core.graph import get_conversation_history
            from src.core.rag.retriever import get_retriever
            
            history = await get_conversation_history(user_id)
            context = "\n".join([
                f"{'Клиент' if h['role'] == 'user' else 'Бот'}: {h['content']}" 
                for h in history[-6:]
            ])
            
            # Get relevant products (NOT async!)
            retriever = get_retriever()
            result = await retriever.retrieve(query=user_query, top_k=10)
            # Products могут быть dict или Pydantic model
            if result.products:
                products = []
                for p in result.products:
                    if hasattr(p, 'model_dump'):
                        products.append(p.model_dump())
                    elif isinstance(p, dict):
                        products.append(p)
                    else:
                        products.append(vars(p))
            else:
                products = []
            
            # Detect order intent
            intent = await detect_order_intent(
                user_message=user_query,
                conversation_context=context,
                available_products=products,
            )
            
            if intent.is_order and intent.items and intent.confidence >= 0.7:
                # Start order flow
                from src.bot.handlers.order import start_order_from_cart
                await start_order_from_cart(message, state, intent.items)
                return

        # Regular conversation processing through LangGraph
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