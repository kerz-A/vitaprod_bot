"""
Order intent detection and item extraction.
Uses LLM to detect order intent and extract items from conversation.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.integrations.llm import get_default_llm

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    """Detected order intent."""
    is_order: bool
    items: list[dict]  # [{name, quantity, price, category, product_form}]
    confidence: float


# Simple pattern-based detection for common order phrases
# ВАЖНО: НЕ включаем простые "да", "оформить" без контекста - 
# они должны обрабатываться только если есть товары в контексте
ORDER_PATTERNS = [
    # Прямые намерения с товаром/количеством
    r'хочу\s+заказать',
    r'хочу\s+\w+\s+\d+',  # хочу чернику 10
    r'закажу\s+\w+',
    r'возьму\s+\w+',
    r'куплю\s+\w+',
    r'беру\s+\w+',
    # Потребности с количеством
    r'мне\s+нужн[оа]\s+\w+',
    r'нужно\s+\d+\s*(кг|килограмм)',
    r'надо\s+\d+\s*(кг|килограмм)',
    # Количество + товар
    r'\d+\s*(кг|килограмм)\s+\w+',
    r'\w+\s+\d+\s*(кг|килограмм)',
]

ORDER_PATTERN = re.compile('|'.join(ORDER_PATTERNS), re.IGNORECASE)

# Паттерны для подтверждения заказа (требуют наличия товаров в контексте)
CONFIRMATION_PATTERNS = [
    r'^да[,!.]?\s*$',
    r'^да[,.]?\s*(хочу|оформ|заказ|давай)',
    r'^хочу[!.]?\s*$',
    r'^оформляй',
    r'^оформляем',
    r'^оформить',
    r'^заказываю',
    r'^заказывай',
    r'хочу\s+оформить',
    r'давай\s+оформ',
]

CONFIRMATION_PATTERN = re.compile('|'.join(CONFIRMATION_PATTERNS), re.IGNORECASE)


def quick_order_check(text: str) -> bool:
    """Quick pattern-based check for order intent."""
    # Проверяем явные заказы с товарами
    if ORDER_PATTERN.search(text):
        return True
    return False


def is_order_confirmation(text: str) -> bool:
    """Check if text is an order confirmation (да, оформить, etc.)"""
    return bool(CONFIRMATION_PATTERN.search(text.strip()))


EXTRACT_ORDER_PROMPT = """Проанализируй диалог и определи:
1. Хочет ли клиент оформить заказ?
2. Какие товары и в каком количестве он хочет заказать?

ВАЖНО: Клиент мог указать товары и количество в ПРЕДЫДУЩИХ сообщениях диалога!
Например: 
- Бот показал: "Черника — 50 кг × 420 ₽ = 21 000 ₽. Хотите оформить?"
- Клиент написал: "да"
В этом случае is_order=true и нужно извлечь товары из контекста бота.

Контекст диалога (последние сообщения):
{conversation_context}

Текущее сообщение клиента:
{user_message}

Доступные товары из базы:
{available_products}

Ответь ТОЛЬКО в формате JSON:
{{
    "is_order": true/false,
    "items": [
        {{
            "name": "название товара из базы",
            "quantity": число_в_кг,
            "price": цена_за_кг,
            "category": "категория",
            "product_form": "Замороженные/Сушёные",
            "origin_country": "страна или null"
        }}
    ],
    "confidence": 0.0-1.0
}}

Правила:
- is_order=true ТОЛЬКО если:
  1. Клиент явно подтверждает заказ ("да", "оформить", "оформляй") И в контексте есть товары с ценами
  2. ИЛИ клиент называет товары с количеством ("хочу чернику 10 кг")
- is_order=false если клиент просто спрашивает про товары без явного желания заказать
- Извлекай товары из ВСЕГО контекста диалога
- Используй цены из списка доступных товаров
- confidence=0.9 для явных заказов с количеством
- confidence=0.8 для подтверждений "да" с товарами в контексте
- confidence=0.0 если нет товаров или количества
"""


async def detect_order_intent(
    user_message: str,
    conversation_context: str,
    available_products: list[dict],
) -> OrderIntent:
    """
    Detect if user wants to place an order and extract items.
    
    Args:
        user_message: Current user message
        conversation_context: Recent conversation history
        available_products: Products found by retriever
        
    Returns:
        OrderIntent with detection results
    """
    # Format available products
    products_text = ""
    for p in available_products:
        if p.get("is_available", True):  # Only show available products
            origin = f" ({p.get('origin_country')})" if p.get('origin_country') else ""
            products_text += (
                f"- {p.get('name')}{origin} [{p.get('category')}] "
                f"({p.get('product_form')}) — {p.get('price')} ₽/кг\n"
            )
    
    if not products_text:
        products_text = "Товары не найдены"
    
    # Use LLM for extraction
    llm = get_default_llm()
    
    prompt = EXTRACT_ORDER_PROMPT.format(
        conversation_context=conversation_context or "Начало диалога",
        user_message=user_message,
        available_products=products_text,
    )
    
    try:
        response = await llm.generate(
            prompt=prompt,
            system_prompt="Ты помощник для извлечения информации о заказах. Отвечай только JSON.",
            temperature=0.1,
            max_tokens=500,
        )
        
        # Parse JSON from response
        content = response.content.strip()
        
        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            
            return OrderIntent(
                is_order=data.get("is_order", False),
                items=data.get("items", []),
                confidence=data.get("confidence", 0.0),
            )
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse order intent JSON: {e}")
    except Exception as e:
        logger.error(f"Error detecting order intent: {e}", exc_info=True)
    
    return OrderIntent(is_order=False, items=[], confidence=0.0)


def format_order_suggestion(items: list[dict]) -> str:
    """Format order suggestion message."""
    lines = ["📦 <b>Оформляем заказ?</b>\n"]
    
    total_quantity = 0
    total_price = 0
    
    for item in items:
        quantity = item.get("quantity", 0)
        price = item.get("price", 0)
        item_total = quantity * price
        total_quantity += quantity
        total_price += item_total
        
        origin = f" ({item.get('origin_country')})" if item.get("origin_country") else ""
        lines.append(
            f"• {item.get('name')}{origin} ({item.get('product_form', '').lower()}) — "
            f"{quantity:.0f} кг × {price:.0f} ₽ = {item_total:.0f} ₽"
        )
    
    lines.append(f"\n<b>Итого:</b> {total_quantity:.0f} кг — {total_price:.0f} ₽")
    
    return "\n".join(lines)