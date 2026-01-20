#!/usr/bin/env python3
"""
Script to load price list into database.

Usage:
    python scripts/load_price.py path/to/price_list.pdf
    python scripts/load_price.py path/to/price_list.xlsx --reasons reasons.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.loaders.price_loader import load_price_list
from src.db.sqlite import db


async def main(file_path: str, reasons_file: str | None = None) -> None:
    """Load price list from file."""
    file_path = Path(file_path)

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Load reasons if provided
    price_reasons = {}
    if reasons_file:
        reasons_path = Path(reasons_file)
        if reasons_path.exists():
            with open(reasons_path, "r", encoding="utf-8") as f:
                reasons_data = json.load(f)
                # Get reasons for the most recent date
                if reasons_data:
                    latest_date = max(reasons_data.keys())
                    price_reasons = reasons_data[latest_date]
                    print(f"Loaded price reasons from {latest_date}")

    # Initialize database
    await db.init()

    print(f"Loading price list from: {file_path}")
    print("-" * 50)

    try:
        stats = await load_price_list(file_path, price_reasons)

        print(f"✅ Successfully loaded price list!")
        print(f"   Date: {stats['date']}")
        print(f"   Total products: {stats['total_products']}")
        print(f"   Available: {stats['available_products']}")
        print(f"   New products: {stats['new_products']}")
        print(f"   Price changes: {stats['price_changes']}")
        print(f"   Newly available: {stats['newly_available']}")

    except Exception as e:
        print(f"❌ Error loading price list: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load price list into database")
    parser.add_argument("file", help="Path to price list file (PDF or XLSX)")
    parser.add_argument(
        "--reasons",
        "-r",
        help="Path to JSON file with price change reasons",
        default=None,
    )

    args = parser.parse_args()
    asyncio.run(main(args.file, args.reasons))
