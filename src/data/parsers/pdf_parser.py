"""
PDF parser for VitaProd price lists.
Extracts product names, prices, and categories from PDF files.
Handles two-column layout with prices in different columns.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pdfplumber


@dataclass
class ParsedProduct:
    """Parsed product data from price list."""

    name: str
    category: str
    price: float | None  # None if not available (marked as '-')
    is_available: bool
    origin_country: str | None = None  # Extracted from name, e.g., '/Китай/'


@dataclass
class ParsedPriceList:
    """Complete parsed price list."""

    date: datetime
    products: list[ParsedProduct]
    source_file: str


class PDFPriceParser:
    """Parser for VitaProd PDF price lists."""

    # Categories we expect to find in text
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

    # Pattern to extract date from header
    DATE_PATTERN = re.compile(r"от\s+(\d{2})\.(\d{2})\.(\d{4})")

    # Pattern to find price in cell
    PRICE_PATTERN = re.compile(r"([\d\s]+[,.]?\d*)\s*₽")

    def __init__(self):
        self.current_category: str | None = None

    def parse(self, file_path: str | Path) -> ParsedPriceList:
        """
        Parse PDF price list file.

        Args:
            file_path: Path to PDF file

        Returns:
            ParsedPriceList with all products
        """
        file_path = Path(file_path)
        products: list[ParsedProduct] = []
        price_date: datetime | None = None

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Try to extract date from first page
                    if price_date is None:
                        price_date = self._extract_date(text)

                    # Try to detect category from page text
                    self._detect_category_from_text(text)

                    # Extract tables from page
                    tables = page.extract_tables()
                    for table in tables:
                        page_products = self._parse_table(table, text)
                        products.extend(page_products)

        return ParsedPriceList(
            date=price_date or datetime.now(),
            products=products,
            source_file=file_path.name,
        )

    def _extract_date(self, text: str) -> datetime | None:
        """Extract date from price list header."""
        match = self.DATE_PATTERN.search(text)
        if match:
            day, month, year = match.groups()
            return datetime(int(year), int(month), int(day))
        return None

    def _detect_category_from_text(self, text: str) -> None:
        """Try to detect current category from page text."""
        text_upper = text.upper()
        for cat in self.KNOWN_CATEGORIES:
            if cat in text_upper:
                self.current_category = cat
                break

    def _parse_table(self, table: list[list], page_text: str = "") -> list[ParsedProduct]:
        """Parse a single table from PDF with two-column layout."""
        products = []

        # Detect category from page text if possible
        page_text_upper = page_text.upper()
        detected_category = None
        for cat in self.KNOWN_CATEGORIES:
            if cat in page_text_upper:
                detected_category = cat
                break

        if detected_category:
            self.current_category = detected_category

        for row in table:
            if not row or len(row) < 2:
                continue

            # Skip header rows
            first_cell = self._clean_text(row[0]) if row[0] else ""
            if first_cell.lower() in ["наименование", ""] or "цена" in first_cell.lower():
                continue
            if first_cell.lower() == "за 1 кг":
                continue

            # Try to extract product from this row
            # The PDF has two-column layout, so we need to check multiple positions

            # Try left column (positions 0-2 for name, 3 for price)
            left_product = self._try_parse_row_variant(row, name_positions=[0], price_positions=[3, 4])
            if left_product:
                products.append(left_product)

            # Try right column (positions 1 for name, 4 for price)
            right_product = self._try_parse_row_variant(row, name_positions=[1], price_positions=[4, 3])
            if right_product:
                products.append(right_product)

        return products

    def _try_parse_row_variant(
        self, row: list, name_positions: list[int], price_positions: list[int]
    ) -> ParsedProduct | None:
        """Try to parse product from specific positions in row."""
        # Find name
        name = ""
        for pos in name_positions:
            if pos < len(row) and row[pos]:
                candidate = self._clean_text(row[pos])
                if candidate and candidate.lower() not in ["наименование", "цена", "за 1 кг", ""]:
                    name = candidate
                    break

        if not name:
            return None

        # Skip if this looks like a header or category
        if name.upper() in self.KNOWN_CATEGORIES:
            self.current_category = name.upper()
            return None

        # Find price
        price = None
        is_available = False

        for pos in price_positions:
            if pos < len(row) and row[pos]:
                cell_value = str(row[pos])
                price, is_available = self._parse_price(cell_value)
                if price is not None or "- ₽" in cell_value or cell_value.strip() == "-":
                    # Found a valid price cell (either with price or explicitly unavailable)
                    if "- ₽" in cell_value or cell_value.strip() == "-":
                        is_available = False
                        price = None
                    break

        # Extract country from name if present
        origin_country = self._extract_country(name)

        return ParsedProduct(
            name=name,
            category=self.current_category or "ПРОЧЕЕ",
            price=price,
            is_available=is_available,
            origin_country=origin_country,
        )

    def _parse_price(self, price_str: str) -> tuple[float | None, bool]:
        """
        Parse price string.

        Returns:
            Tuple of (price, is_available)
            Price is None if product is unavailable
        """
        if not price_str:
            return None, False

        price_str = str(price_str).strip()

        # Check for unavailable markers
        if price_str in ["-", "–", "—", ""] or "- ₽" in price_str:
            return None, False

        # Try to extract price with regex
        match = self.PRICE_PATTERN.search(price_str)
        if match:
            price_value = match.group(1)
            # Clean up: remove spaces, replace comma with dot
            cleaned = price_value.replace(" ", "").replace(",", ".").strip()
            try:
                price = float(cleaned)
                return price, True
            except ValueError:
                pass

        # Fallback: try direct parsing
        cleaned = price_str.replace("₽", "").replace(" ", "").replace(",", ".").strip()
        try:
            price = float(cleaned)
            return price, True
        except ValueError:
            return None, False

    def _extract_country(self, name: str) -> str | None:
        """Extract country from product name (e.g., 'Вишня без косточки /Китай/')."""
        match = self.COUNTRY_PATTERN.search(name)
        if match:
            return match.group(1)
        return None

    def _clean_text(self, text: str | None) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        # Replace multiple spaces/newlines with single space
        cleaned = re.sub(r"\s+", " ", str(text)).strip()
        return cleaned


def parse_price_list(file_path: str | Path) -> ParsedPriceList:
    """Convenience function to parse a price list file."""
    parser = PDFPriceParser()
    return parser.parse(file_path)
