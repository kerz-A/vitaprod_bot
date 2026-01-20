"""
XLSX parser for VitaProd price lists.
Extracts product names, prices, and categories from Excel files.
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.data.parsers.pdf_parser import ParsedPriceList, ParsedProduct


class XLSXPriceParser:
    """Parser for VitaProd XLSX price lists."""

    # Categories we expect to find
    KNOWN_CATEGORIES = [
        "ЯГОДЫ ЗАМОРОЖЕННЫЕ",
        "ОВОЩИ ЗАМОРОЖЕННЫЕ",
        "ФРУКТЫ ЗАМОРОЖЕННЫЕ",
        "ГРИБЫ ЗАМОРОЖЕННЫЕ",
        "КОМПОТНЫЕ СМЕСИ ЗАМОРОЖЕННЫЕ",
        "ОВОЩНЫЕ СМЕСИ ЗАМОРОЖЕННЫЕ",
        "ПЛОДЫ СУШЁНЫЕ",
        "ГРИБЫ СУШЁНЫЕ",
        "ОРЕХИ ЗАМОРОЖЕННЫЕ",
        "ТРАВЫ СУШЁНЫЕ",
    ]

    # Pattern to extract country from product name
    COUNTRY_PATTERN = re.compile(r"/([^/]+)/")

    # Pattern to extract date from filename or sheet
    DATE_PATTERN = re.compile(r"(\d{2})[\._]?(\d{2})[\._]?(\d{2,4})")

    def parse(self, file_path: str | Path) -> ParsedPriceList:
        """
        Parse XLSX price list file.

        Args:
            file_path: Path to XLSX file

        Returns:
            ParsedPriceList with all products
        """
        file_path = Path(file_path)
        products: list[ParsedProduct] = []

        # Try to extract date from filename
        price_date = self._extract_date_from_filename(file_path.name)

        # Read Excel file
        df = pd.read_excel(file_path, header=None)

        current_category = None

        for idx, row in df.iterrows():
            # Get first cell value
            first_cell = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""

            # Check if this is a category header
            if first_cell.upper() in self.KNOWN_CATEGORIES:
                current_category = first_cell.upper()
                continue

            # Skip header rows
            if first_cell.lower() in ["наименование", ""] or "цена" in first_cell.lower():
                continue

            # Skip empty or invalid rows
            if not first_cell or first_cell.lower() == "nan":
                continue

            # This should be a product row
            product = self._parse_row(row, current_category)
            if product:
                products.append(product)

        return ParsedPriceList(
            date=price_date or datetime.now(),
            products=products,
            source_file=file_path.name,
        )

    def _parse_row(self, row: pd.Series, category: str | None) -> ParsedProduct | None:
        """Parse a single row from DataFrame."""
        name = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if not name or name.lower() == "nan":
            return None

        # Try to get price from second column
        price_val = row.iloc[1] if len(row) > 1 else None
        price, is_available = self._parse_price(price_val)

        # Extract country from name if present
        origin_country = self._extract_country(name)

        return ParsedProduct(
            name=name,
            category=category or "ПРОЧЕЕ",
            price=price,
            is_available=is_available,
            origin_country=origin_country,
        )

    def _parse_price(self, price_val) -> tuple[float | None, bool]:
        """
        Parse price value.

        Returns:
            Tuple of (price, is_available)
        """
        if pd.isna(price_val):
            return None, False

        price_str = str(price_val).strip()

        if price_str in ["-", "–", "—", "", "nan"]:
            return None, False

        # Remove currency symbols and spaces
        cleaned = price_str.replace("₽", "").replace(" ", "").replace(",", ".").strip()

        try:
            price = float(cleaned)
            return price, True
        except ValueError:
            return None, False

    def _extract_country(self, name: str) -> str | None:
        """Extract country from product name."""
        match = self.COUNTRY_PATTERN.search(name)
        if match:
            return match.group(1)
        return None

    def _extract_date_from_filename(self, filename: str) -> datetime | None:
        """Try to extract date from filename."""
        match = self.DATE_PATTERN.search(filename)
        if match:
            day, month, year = match.groups()
            year = int(year)
            if year < 100:
                year += 2000
            try:
                return datetime(year, int(month), int(day))
            except ValueError:
                pass
        return None


def parse_xlsx_price_list(file_path: str | Path) -> ParsedPriceList:
    """Convenience function to parse an XLSX price list file."""
    parser = XLSXPriceParser()
    return parser.parse(file_path)
