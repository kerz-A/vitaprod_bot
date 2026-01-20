#!/usr/bin/env python3
"""
Script to initialize database tables.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.sqlite import db
from src.db.vector import vector_db


async def main() -> None:
    """Initialize all databases."""
    print("Initializing databases...")
    print("-" * 50)

    # Initialize SQLite
    print("Creating SQLite tables...")
    await db.init()
    print("✅ SQLite initialized")

    # Initialize Qdrant collection
    print("Creating Qdrant collection...")
    await vector_db.init_collection()
    print("✅ Qdrant collection created")

    print("-" * 50)
    print("✅ All databases initialized successfully!")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
