"""
Bot handlers registration.
"""

from aiogram import Dispatcher

from src.bot.handlers.start import router as start_router
from src.bot.handlers.price_query import router as price_query_router
from src.bot.handlers.order import router as order_router


def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers to dispatcher."""
    # Order matters! Start handler should be first, then orders (for FSM), then price query
    dp.include_router(start_router)
    dp.include_router(order_router)  # Order FSM handlers
    dp.include_router(price_query_router)
