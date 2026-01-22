"""
Conversation state for LangGraph.
Defines the structure of conversation state and message history.
"""

from typing import Annotated, Optional, TypedDict
from langgraph.graph.message import add_messages


class ConversationState(TypedDict):
    """
    State of the conversation.
    
    Attributes:
        messages: List of conversation messages (auto-accumulated by add_messages)
        user_id: Telegram user ID
        user_name: User's display name
        current_products: Products from last retrieval
        cart: Current order items (for order collection flow)
        intent: Detected user intent
    """
    # Messages are accumulated automatically by LangGraph
    messages: Annotated[list, add_messages]
    
    # User info
    user_id: int
    user_name: Optional[str]
    
    # RAG context
    current_products: list[dict]
    
    # Order state (for future order flow)
    cart: list[dict]
    
    # Intent classification
    intent: Optional[str]  # 'question', 'order', 'greeting', 'complaint'
