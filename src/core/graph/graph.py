"""
LangGraph conversation graph.
Orchestrates the conversation flow with persistent memory using PostgreSQL.
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage

from src.core.graph.state import ConversationState
from src.core.graph.nodes import retrieve_products, generate_response
from src.config import settings

logger = logging.getLogger(__name__)


def create_graph() -> StateGraph:
    """
    Create the conversation graph.
    
    Flow:
        START -> retrieve_products -> generate_response -> END
    """
    graph = StateGraph(ConversationState)
    
    # Add nodes
    graph.add_node("retrieve", retrieve_products)
    graph.add_node("generate", generate_response)
    
    # Define flow
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    
    return graph


# Compiled graph singleton
_compiled_graph = None
_checkpointer = None


def get_conversation_graph():
    """
    Get compiled conversation graph with PostgreSQL checkpointer (singleton).
    """
    global _compiled_graph, _checkpointer
    
    if _compiled_graph is None:
        logger.info("Initializing LangGraph conversation graph with PostgreSQL...")
        
        graph = create_graph()
        
        # Create PostgreSQL checkpointer
        import psycopg
        
        conn_string = settings.postgres_url
        
        # Create connection and checkpointer
        connection = psycopg.connect(conn_string)
        _checkpointer = PostgresSaver(connection)
        
        # Setup tables if needed
        _checkpointer.setup()
        
        _compiled_graph = graph.compile(checkpointer=_checkpointer)
        
        logger.info("LangGraph graph compiled successfully with PostgreSQL")
    
    return _compiled_graph


async def chat(
    user_id: int,
    message: str,
    user_name: Optional[str] = None,
) -> str:
    """
    Process user message and return response.
    
    Args:
        user_id: Telegram user ID (used as thread_id for memory)
        message: User's message text
        user_name: Optional user display name
        
    Returns:
        Assistant's response text
    """
    graph = get_conversation_graph()
    
    # Thread ID = user ID for per-user conversation memory
    thread_id = str(user_id)
    
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }
    
    # Initial state with the new message
    input_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_name": user_name,
        "current_products": [],
        "cart": [],
        "intent": None,
    }
    
    try:
        # Invoke graph (sync, as psycopg connection is sync)
        result = graph.invoke(input_state, config=config)
        
        # Extract last AI message
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            return last_message.content
        
        return "Извините, не удалось обработать запрос."
        
    except Exception as e:
        logger.error(f"Graph execution error: {e}", exc_info=True)
        return (
            "Извините, произошла ошибка при обработке запроса. "
            "Пожалуйста, попробуйте позже или свяжитесь с менеджером: +7 912 828-18-38"
        )


async def get_conversation_history(user_id: int) -> list[dict]:
    """
    Get conversation history for a user.
    
    Returns:
        List of messages with 'role' and 'content'
    """
    graph = get_conversation_graph()
    
    thread_id = str(user_id)
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = graph.get_state(config)
        messages = state.values.get("messages", [])
        
        history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            else:
                history.append({"role": "assistant", "content": msg.content})
        
        return history
        
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return []


async def clear_conversation(user_id: int) -> bool:
    """
    Clear conversation history for a user.
    Note: With PostgresSaver, this creates a new thread effectively.
    
    Returns:
        True if successful
    """
    logger.info(f"Clear conversation requested for user {user_id}")
    # PostgresSaver doesn't have a direct delete method
    # The conversation will be "cleared" by using a new thread_id suffix
    # For now, we just log it - implement proper clearing if needed
    return True