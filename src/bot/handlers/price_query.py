"""
Message handler - main conversation handler using LangGraph.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from src.core.graph import chat
from src.core.orders.states import OrderStates
from src.core.orders.intent import (
    detect_order_intent, 
    format_order_suggestion, 
    quick_order_check,
    is_order_confirmation,
)
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
    
    # Check if user is in ANY order FSM state - skip ALL processing, let order handlers deal with it
    current_state = await state.get_state()
    if current_state and "OrderStates" in str(current_state):
        # User is in order flow - don't interfere
        # Order handlers will process this message
        logger.debug(f"User {message.from_user.id} in order state {current_state}, skipping price_query handler")
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
        order_started = False
        
        # Check for order confirmation ("да", "оформить") - needs context check
        if is_order_confirmation(user_query):
            try:
                order_started = await try_start_order_from_confirmation(message, state, user_id, user_query)
            except Exception as e:
                logger.warning(f"Order confirmation handling failed: {e}")
                order_started = False
        
        # Check for explicit order intent with products ("хочу чернику 10 кг")
        elif quick_order_check(user_query):
            try:
                order_started = await try_start_order(message, state, user_id, user_query)
            except Exception as e:
                logger.warning(f"Order intent detection failed, falling back to chat: {e}")
                order_started = False
        
        if order_started:
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
            "Пожалуйста, попробуйте переформулировать вопрос или свяжитесь с менеджером:\n"
            "📞 +7 912 828-18-38"
        )


async def try_start_order_from_confirmation(
    message: Message, 
    state: FSMContext, 
    user_id: int, 
    user_query: str
) -> bool:
    """
    Handle order confirmation ("да", "оформить").
    Extract items from conversation context and start order.
    """
    from src.core.graph import get_conversation_history
    from src.core.rag.retriever import get_retriever
    
    # Get conversation history - we need it to find items
    history = await get_conversation_history(user_id)
    
    if not history or len(history) < 2:
        # No context - can't confirm order without previous messages
        logger.info("No conversation history for order confirmation")
        return False
    
    # Build context from recent messages
    context = "\n".join([
        f"{'Клиент' if h['role'] == 'user' else 'Бот'}: {h['content']}" 
        for h in history[-8:]
    ])
    
    # Check if there are items mentioned in recent bot responses
    recent_bot_messages = [h['content'] for h in history[-6:] if h['role'] == 'assistant']
    
    # Look for price patterns in bot messages (indicates items were shown)
    has_items_in_context = any(
        '₽' in msg and ('кг' in msg or 'Итого' in msg)
        for msg in recent_bot_messages
    )
    
    if not has_items_in_context:
        # No items in context - can't confirm
        logger.info("No items in conversation context for confirmation")
        return False
    
    # Get products that might be relevant
    # Search based on recent user messages
    recent_user_messages = " ".join([h['content'] for h in history[-6:] if h['role'] == 'user'])
    
    retriever = get_retriever()
    result = await retriever.retrieve(query=recent_user_messages, top_k=15)
    
    products = []
    if result and result.products:
        for p in result.products:
            if hasattr(p, 'model_dump'):
                products.append(p.model_dump())
            elif isinstance(p, dict):
                products.append(p)
            else:
                products.append(vars(p))
    
    if not products:
        logger.info("No products found for order confirmation")
        return False
    
    # Use LLM to extract items from context
    intent = await detect_order_intent(
        user_message=user_query,
        conversation_context=context,
        available_products=products,
    )
    
    if intent.is_order and intent.items and intent.confidence >= 0.7:
        # Start order flow
        from src.bot.handlers.order import start_order_from_cart
        await start_order_from_cart(message, state, intent.items)
        return True
    
    return False


async def try_start_order(message: Message, state: FSMContext, user_id: int, user_query: str) -> bool:
    """
    Try to detect order intent and start order flow.
    Returns True if order flow was started, False otherwise.
    """
    from src.core.graph import get_conversation_history
    from src.core.rag.retriever import get_retriever
    
    # Get conversation context for intent detection
    history = await get_conversation_history(user_id)
    context = "\n".join([
        f"{'Клиент' if h['role'] == 'user' else 'Бот'}: {h['content']}" 
        for h in history[-6:]
    ]) if history else ""
    
    # Get relevant products
    retriever = get_retriever()
    result = await retriever.retrieve(query=user_query, top_k=10)
    
    # Products могут быть dict или Pydantic model
    products = []
    if result and result.products:
        for p in result.products:
            if hasattr(p, 'model_dump'):
                products.append(p.model_dump())
            elif isinstance(p, dict):
                products.append(p)
            else:
                products.append(vars(p))
    
    # If no products found - don't try to create order
    if not products:
        logger.info("No products found for order intent, falling back to chat")
        return False
    
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
        return True
    
    return False