"""
Graph nodes for conversation processing.
Each node is a function that takes state and returns updated state.
"""

import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.core.graph.state import ConversationState
from src.core.rag.retriever import get_retriever
from src.core.prompts import (
    build_system_prompt,
    build_user_prompt,
    format_products_context,
    format_conversation_history,
)
from src.integrations.llm import get_default_llm

logger = logging.getLogger(__name__)


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
        
        # FIX BUG #5: Подробное логирование найденных товаров
        logger.info(
            f"Retrieved {len(result.products)} products for query: '{user_query[:80]}'"
        )
        for i, (product, score) in enumerate(zip(result.products, result.scores)):
            logger.info(
                f"  [{i+1}] score={score:.3f} | {product.get('name')} | "
                f"{product.get('product_form')} | "
                f"price={product.get('price')} | "
                f"available={product.get('is_available')}"
            )
        
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
        return {"messages": [AIMessage(content="Здравствуйте! С вами консультант компании ВитаПрод — Себастьян Перейра. Чем могу помочь?")]}
    
    # Build prompt with conversation history and products
    llm = get_default_llm()
    
    # Format conversation history (exclude last message - it's the current query)
    history = format_conversation_history(messages[:-1])
    
    # Format products context
    products_context = format_products_context(products)
    
    # Get last user message
    last_message = messages[-1].content if messages else ""
    
    # Build prompts using new prompt module
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        conversation_history=history,
        products_context=products_context,
        user_query=last_message,
    )

    # FIX BUG #5: Логируем полный промпт для отладки
    logger.debug(f"=== USER PROMPT ===\n{user_prompt}\n=== END PROMPT ===")

    try:
        response = await llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.05,  # FIX BUG #3: Снижена temperature с 0.3 до 0.05
            max_tokens=512,
        )
        
        response_text = response.content
        
        # FIX BUG #4: Валидация ответа — проверяем, что цены совпадают с контекстом
        response_text = _validate_and_warn(response_text, products)
        
        logger.info(f"Generated response for user query: '{last_message[:50]}...'")
        logger.debug(f"Response: {response_text[:200]}...")
        
        return {"messages": [AIMessage(content=response_text)]}
    
    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        return {
            "messages": [
                AIMessage(
                    content="Извините, произошла ошибка. Пожалуйста, попробуйте ещё раз или свяжитесь с менеджером: +7 912 828-18-38"
                )
            ]
        }


def _validate_and_warn(response_text: str, products: list[dict]) -> str:
    """
    FIX BUG #4: Проверяет, что цены в ответе LLM совпадают с данными из RAG.
    Если найдены подозрительные цены — логирует предупреждение.
    
    В будущем можно добавить автозамену неверных цен.
    """
    if not products:
        return response_text
    
    # Собираем реальные цены из RAG-контекста
    known_prices = {}
    for p in products:
        name = p.get("name", "").lower()
        price = p.get("price")
        if name and price:
            known_prices[name] = price
    
    # Ищем цены в ответе LLM (паттерн: число + ₽)
    price_mentions = re.findall(r'(\d+)\s*₽', response_text)
    
    for price_str in price_mentions:
        price_val = float(price_str)
        # Проверяем, есть ли такая цена среди реальных
        real_prices = set(known_prices.values())
        if real_prices and price_val not in real_prices:
            # Цена из ответа не совпадает ни с одной реальной
            logger.warning(
                f"⚠️ HALLUCINATION DETECTED: LLM mentioned price {price_val}₽, "
                f"but known prices are: {real_prices}. "
                f"Response: {response_text[:200]}..."
            )
            # Пока только логируем. Для автоматической замены нужна более сложная логика.
    
    return response_text


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
