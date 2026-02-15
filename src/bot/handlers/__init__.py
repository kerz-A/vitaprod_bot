"""
Bot handlers registration.
"""

from aiogram import Dispatcher


def register_handlers(dp: Dispatcher) -> None:
    """Register all bot handlers."""
    
    # Import routers
    from src.bot.handlers.start import router as start_router
    from src.bot.handlers.order import router as order_router
    from src.bot.handlers.price_query import router as price_query_router
    
    # Try to import voice router (optional, requires STT configuration)
    try:
        from src.bot.handlers.voice import router as voice_router
        has_voice = True
    except ImportError:
        has_voice = False
    
    # Register routers in order of priority
    # Order matters! More specific routers should come first.
    
    # 1. Start commands and menu buttons
    dp.include_router(start_router)
    
    # 2. Order flow (FSM-based)
    dp.include_router(order_router)
    
    # 3. Voice messages (before text messages)
    if has_voice:
        dp.include_router(voice_router)
    
    # 4. Regular text messages (catch-all, should be last)
    dp.include_router(price_query_router)