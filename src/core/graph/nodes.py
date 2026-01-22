"""
Graph nodes for conversation processing.
Each node is a function that takes state and returns updated state.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.core.graph.state import ConversationState
from src.core.rag.retriever import get_retriever
from src.core.rag.prompts import build_system_prompt, format_product_context
from src.integrations.llm import get_default_llm

logger = logging.getLogger(__name__)


# System prompt with conversation context instructions
SYSTEM_PROMPT_WITH_MEMORY = """Ты — вежливый и профессиональный консультант компании ВитаПрод, специализирующейся на продаже замороженных ягод, овощей, фруктов и грибов оптом.

Твоя задача — помогать клиентам с информацией о товарах, ценах и наличии.

ВАЖНО - КОНТЕКСТ ДИАЛОГА:
- Ты ведёшь непрерывный диалог с клиентом
- Помни о чём говорили раньше в этом диалоге
- Если клиент спрашивает "а этот?", "в каком виде?", "а цена?" — он имеет в виду товары, которые обсуждались ранее
- Используй историю диалога для понимания контекста

Правила ответов:
1. Отвечай только на основе предоставленной информации о товарах
2. Если товар есть в наличии — называй точную цену за 1 кг
3. Если товара нет в наличии — так и скажи
4. Если спрашивают о форме товара (замороженный/сушёный) — обязательно укажи эту информацию
5. Будь краток, но информативен
6. Используй дружелюбный, но профессиональный тон

Контакты для связи с менеджером:
- Телефон: +7 912 828-18-38
- WhatsApp/Viber: +7 912 828-18-38
- Email: vitaprod43@mail.ru

Адрес: город Киров, переулок Энгельса, 2"""


async def retrieve_products(state: ConversationState) -> dict:
    """
    Retrieve relevant products based on user query.
    Uses the last user message and conversation context.
    """
    messages = state.get("messages", [])
    
    if not messages:
        return {"current_products": []}
    
    # Get last user message
    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        return {"current_products": []}
    
    user_query = last_message.content
    
    # Build context query from conversation history
    # Include recent context for better retrieval
    context_query = _build_context_query(messages, user_query)
    
    try:
        retriever = get_retriever()
        result = await retriever.retrieve(query=context_query)
        
        logger.info(f"Retrieved {len(result.products)} products for query: {user_query[:50]}")
        
        return {"current_products": result.products}
    
    except Exception as e:
        logger.error(f"Retrieval error: {e}", exc_info=True)
        return {"current_products": []}


async def generate_response(state: ConversationState) -> dict:
    """
    Generate response using LLM with conversation history and retrieved products.
    """
    messages = state.get("messages", [])
    products = state.get("current_products", [])
    
    if not messages:
        return {"messages": [AIMessage(content="Здравствуйте! Чем могу помочь?")]}
    
    # Build prompt with conversation history and products
    llm = get_default_llm()
    
    # Format conversation history for the prompt
    conversation_history = _format_conversation_history(messages[:-1])  # Exclude last message
    
    # Format current products context
    products_context = format_product_context(products) if products else "Товары не найдены по запросу."
    
    # Get last user message
    last_message = messages[-1].content if messages else ""
    
    # Build the prompt
    user_prompt = f"""История диалога:
{conversation_history}

Информация о найденных товарах:
{products_context}

Текущий вопрос клиента: {last_message}

Ответь на вопрос клиента, учитывая историю диалога и информацию о товарах."""

    try:
        response = await llm.generate(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT_WITH_MEMORY,
            temperature=0.3,
            max_tokens=512,
        )
        
        logger.info(f"Generated response for user query")
        
        return {"messages": [AIMessage(content=response.content)]}
    
    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        return {
            "messages": [
                AIMessage(
                    content="Извините, произошла ошибка. Пожалуйста, попробуйте ещё раз или свяжитесь с менеджером: +7 912 828-18-38"
                )
            ]
        }


def _build_context_query(messages: list, current_query: str) -> str:
    """
    Build enriched query using conversation context.
    Helps retrieve relevant products when user asks follow-up questions.
    """
    # If it's a short/context-dependent query, enrich with recent context
    context_indicators = [
        "этот", "этот товар", "этого", "эта", "эти",
        "он", "она", "оно", "они",
        "его", "её", "их",
        "такой", "такая", "такое", "такие",
        "а цена", "а стоимость", "сколько стоит",
        "в каком виде", "какой вид", "форма",
        "а есть", "есть ли",
    ]
    
    is_context_dependent = (
        len(current_query.split()) <= 4 or
        any(ind in current_query.lower() for ind in context_indicators)
    )
    
    if is_context_dependent and len(messages) > 1:
        # Extract product names from recent AI responses
        recent_products = []
        for msg in messages[-6:]:  # Look at last 3 exchanges
            if isinstance(msg, AIMessage):
                # Simple extraction - look for product patterns
                content = msg.content
                # This is a simple heuristic - can be improved
                recent_products.append(content)
        
        # Also look at recent user queries
        recent_queries = []
        for msg in messages[-6:]:
            if isinstance(msg, HumanMessage):
                recent_queries.append(msg.content)
        
        # Combine for better retrieval
        context = " ".join(recent_queries[-2:]) if recent_queries else ""
        enriched_query = f"{context} {current_query}".strip()
        
        logger.debug(f"Enriched query: {enriched_query}")
        return enriched_query
    
    return current_query


def _format_conversation_history(messages: list, max_messages: int = 10) -> str:
    """
    Format conversation history for the prompt.
    Limits to last N messages to fit context window.
    """
    if not messages:
        return "Это начало диалога."
    
    # Take last N messages
    recent_messages = messages[-max_messages:]
    
    lines = []
    for msg in recent_messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Клиент: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Консультант: {msg.content}")
    
    return "\n".join(lines) if lines else "Это начало диалога."
