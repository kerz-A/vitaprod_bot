"""
Telegram bot initialization and configuration.
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings


def create_bot() -> Bot:
    """Create configured Telegram bot instance."""
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Create dispatcher with storage."""
    storage = MemoryStorage()  # Use Redis in production for persistence
    return Dispatcher(storage=storage)


# Global instances
bot: Bot | None = None
dp: Dispatcher | None = None


def get_bot() -> Bot:
    """Get or create bot instance."""
    global bot
    if bot is None:
        bot = create_bot()
    return bot


def get_dispatcher() -> Dispatcher:
    """Get or create dispatcher instance."""
    global dp
    if dp is None:
        dp = create_dispatcher()
    return dp
