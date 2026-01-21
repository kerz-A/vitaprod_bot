"""
Price list loader - imports parsed price data into database and vector store.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.data.embeddings import EmbeddingService  # Must be before parsers (torch DLL loading order)
from src.data.parsers import ParsedPriceList, ParsedProduct, parse_file
from src.db.models import Category, PriceHistory, PriceList, Product
from src.db.sqlite import db
from src.db.vector import vector_db
from typing import Optional, Dict, Tuple


class PriceLoader:
    """Loads price list data into SQLite and Qdrant."""

    def __init__(self):
        self.embedding_service = EmbeddingService()

    async def load_file(
        self,
        file_path: str | Path,
        price_reasons: Optional[Dict[str, str]] = None,
    ) -> dict:
        """
        Load price list from file into database.

        Args:
            file_path: Path to PDF or XLSX file
            price_reasons: Optional dict mapping product names to price change reasons

        Returns:
            Statistics about loaded data
        """
        file_path = Path(file_path)
        price_reasons = price_reasons or {}

        # Parse the file
        parsed = parse_file(file_path)

        stats = {
            "file": file_path.name,
            "date": parsed.date.isoformat(),
            "total_products": len(parsed.products),
            "available_products": 0,
            "new_products": 0,
            "price_changes": 0,
            "newly_available": 0,
        }

        async with db.session() as session:
            # Create price list record
            price_list = PriceList(
                filename=file_path.name,
                date=parsed.date,
                products_count=len(parsed.products),
            )
            session.add(price_list)

            # Process each product
            for parsed_product in parsed.products:
                result = await self._process_product(
                    session=session,
                    parsed_product=parsed_product,
                    price_date=parsed.date,
                    price_reason=price_reasons.get(parsed_product.name),
                )

                if parsed_product.is_available:
                    stats["available_products"] += 1
                if result["is_new"]:
                    stats["new_products"] += 1
                if result["price_changed"]:
                    stats["price_changes"] += 1
                if result["newly_available"]:
                    stats["newly_available"] += 1

            await session.commit()

        # Update vector database
        await self._update_vector_db(parsed.products)

        return stats

    async def _process_product(
        self,
        session: AsyncSession,
        parsed_product: ParsedProduct,
        price_date: datetime,
        price_reason: Optional[str],
    ) -> dict:
        """Process single product - create or update in database."""
        result = {
            "is_new": False,
            "price_changed": False,
            "newly_available": False,
        }

        # Get or create category
        category = await self._get_or_create_category(session, parsed_product.category)

        # Find existing product
        stmt = select(Product).where(
            Product.name == parsed_product.name,
            Product.category_id == category.id,
        )
        db_product = (await session.execute(stmt)).scalar_one_or_none()

        if db_product is None:
            # New product
            db_product = Product(
                name=parsed_product.name,
                category_id=category.id,
                current_price=parsed_product.price,
                is_available=parsed_product.is_available,
                origin_country=parsed_product.origin_country,
            )
            session.add(db_product)
            await session.flush()  # Get the ID
            result["is_new"] = True
            previous_price = None
        else:
            # Existing product - check for changes
            previous_price = db_product.current_price
            was_available = db_product.is_available

            # Check if price changed
            if previous_price != parsed_product.price:
                result["price_changed"] = True

            # Check if became available
            if not was_available and parsed_product.is_available:
                result["newly_available"] = True

            # Update current values
            db_product.current_price = parsed_product.price
            db_product.is_available = parsed_product.is_available
            if parsed_product.origin_country:
                db_product.origin_country = parsed_product.origin_country

        # Add price history record
        history = PriceHistory(
            product_id=db_product.id,
            price=parsed_product.price,
            is_available=parsed_product.is_available,
            date=price_date,
            previous_price=previous_price,
            price_change_reason=price_reason,
        )
        session.add(history)

        return result

    async def _get_or_create_category(
        self, session: AsyncSession, category_name: str
    ) -> Category:
        """Get existing category or create new one."""
        stmt = select(Category).where(Category.name == category_name)
        category = (await session.execute(stmt)).scalar_one_or_none()

        if category is None:
            category = Category(name=category_name)
            session.add(category)
            await session.flush()

        return category

    async def _update_vector_db(self, products: list[ParsedProduct]) -> None:
        """Update vector database with product embeddings."""
        # Prepare data for embedding
        texts = []
        for p in products:
            # Create searchable text
            text = f"{p.name} {p.category}"
            if p.origin_country:
                text += f" {p.origin_country}"
            texts.append(text)

        # Generate embeddings
        embeddings = self.embedding_service.encode(texts)

        # Prepare payloads
        payloads = [
            {
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "is_available": p.is_available,
                "origin_country": p.origin_country,
            }
            for p in products
        ]

        # Use product names as IDs (hash for uniqueness)
        ids = [hash(f"{p.name}_{p.category}") % (2**31) for p in products]

        # Initialize collection if needed
        await vector_db.init_collection()

        # Upsert to Qdrant
        vector_db.upsert_products(ids, embeddings.tolist(), payloads)


async def load_price_list(
    file_path: str | Path,
    price_reasons: Optional[Dict[str, str]] = None,
) -> dict:
    """Convenience function to load a price list."""
    loader = PriceLoader()
    return await loader.load_file(file_path, price_reasons)