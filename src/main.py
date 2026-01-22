"""
VitaProd Telegram Bot - Main entry point.
"""

import asyncio
import logging
import sys

from src.bot.bot import get_bot, get_dispatcher
from src.bot.handlers import register_handlers
from src.db.sqlite import db
from src.db.vector import vector_db
from src.config import settings


# Fix for Windows asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Initialize services on startup."""
    logger.info("Starting VitaProd Bot...")

    # Initialize database
    await db.init()
    logger.info("Database initialized")

    # Initialize vector DB
    await vector_db.init_collection()
    logger.info("Vector database initialized")


async def on_shutdown() -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down VitaProd Bot...")

    await db.close()
    vector_db.close()

    logger.info("Cleanup complete")


async def main() -> None:
    """Main function to run the bot."""
    bot = get_bot()
    dp = get_dispatcher()

    # Register handlers
    register_handlers(dp)

    # Register startup/shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Start polling
    logger.info("Bot is starting...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())