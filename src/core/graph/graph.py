"""
LangGraph conversation graph.
Orchestrates the conversation flow with persistent memory using PostgreSQL.
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
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
_initialized = False


async def init_checkpointer():
    """Initialize the async PostgreSQL checkpointer."""
    global _checkpointer, _initialized
    
    if _initialized:
        return _checkpointer
    
    import psycopg
    
    conn_string = settings.postgres_url
    
    # Setup tables with sync connection (required for CREATE INDEX CONCURRENTLY)
    logger.info("Setting up PostgreSQL checkpointer tables...")
    with psycopg.connect(conn_string, autocommit=True) as setup_conn:
        from langgraph.checkpoint.postgres import PostgresSaver
        sync_checkpointer = PostgresSaver(setup_conn)
        sync_checkpointer.setup()
    
    # Create async checkpointer
    import psycopg_pool
    
    pool = psycopg_pool.AsyncConnectionPool(
        conninfo=conn_string,
        min_size=1,
        max_size=5,
    )
    await pool.open()
    
    _checkpointer = AsyncPostgresSaver(pool)
    _initialized = True
    
    logger.info("AsyncPostgresSaver initialized successfully")
    return _checkpointer


async def get_conversation_graph():
    """
    Get compiled conversation graph with PostgreSQL checkpointer (singleton).
    """
    global _compiled_graph
    
    if _compiled_graph is None:
        logger.info("Initializing LangGraph conversation graph with PostgreSQL...")
        
        graph = create_graph()
        checkpointer = await init_checkpointer()
        
        _compiled_graph = graph.compile(checkpointer=checkpointer)
        
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
    graph = await get_conversation_graph()
    
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
        # Invoke graph asynchronously
        result = await graph.ainvoke(input_state, config=config)
        
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
    graph = await get_conversation_graph()
    
    thread_id = str(user_id)
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = await graph.aget_state(config)
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
    Deletes checkpoints from PostgreSQL for this thread_id.
    
    Returns:
        True if successful
    """
    import psycopg
    
    thread_id = str(user_id)
    logger.info(f"Clearing conversation for user {user_id} (thread_id: {thread_id})")
    
    try:
        conn_string = settings.postgres_url
        
        with psycopg.connect(conn_string) as conn:
            with conn.cursor() as cur:
                # Delete from all checkpoint tables for this thread
                cur.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                    (thread_id,)
                )
                writes_deleted = cur.rowcount
                
                cur.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                    (thread_id,)
                )
                blobs_deleted = cur.rowcount
                
                cur.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s",
                    (thread_id,)
                )
                checkpoints_deleted = cur.rowcount
                
            conn.commit()
        
        logger.info(
            f"Conversation cleared for user {user_id}: "
            f"checkpoints={checkpoints_deleted}, blobs={blobs_deleted}, writes={writes_deleted}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}", exc_info=True)
        return False