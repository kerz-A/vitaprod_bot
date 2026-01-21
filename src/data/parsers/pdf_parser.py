"""
PDF parser for VitaProd price lists.
Extracts product names, prices, categories, and product form from PDF files.
Handles two-column layout where categories can change mid-table.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber


@dataclass
class ParsedProduct:
    """Parsed product data from price list."""

    name: str
    category: str  # e.g., "Ягоды", "Овощи", "Грибы"
    product_form: str  # e.g., "Замороженные", "Сушёные"
    price: Optional[float]  # None if not available (marked as '-')
    is_available: bool
    origin_country: Optional[str] = None  # Extracted from name, e.g., '/Китай/'


@dataclass
class ParsedPriceList:
    """Complete parsed price list."""

    date: datetime
    products: list[ParsedProduct]
    source_file: str


@dataclass
class CategoryHeader:
    """Category header found on page."""
    category: str
    form: str
    x: float
    y: float


class PDFPriceParser:
    """Parser for VitaProd PDF price lists."""

    # Category keywords to look for
    CATEGORY_KEYWORDS = ['ЯГОДЫ', 'ОВОЩИ', 'ГРИБЫ', 'ФРУКТЫ', 'ПЛОДЫ', 'ОРЕХИ', 'ТРАВЫ']
    COMPOUND_CATEGORIES = ['КОМПОТНЫЕ СМЕСИ', 'ОВОЩНЫЕ СМЕСИ']
    FORM_KEYWORDS = ['ЗАМОРОЖЕННЫЕ', 'СУШЕНЫЕ', 'СУШЁНЫЕ']

    # Pattern to extract country from product name
    COUNTRY_PATTERN = re.compile(r"/([^/]+)/")

    # Pattern to extract date from header
    DATE_PATTERN = re.compile(r"от\s+(\d{2})\.(\d{2})\.(\d{4})")

    # Pattern to find price in cell
    PRICE_PATTERN = re.compile(r"([\d\s]+[,.]?\d*)\s*₽")

    def parse(self, file_path: str | Path) -> ParsedPriceList:
        """Parse PDF price list file."""
        file_path = Path(file_path)
        products: list[ParsedProduct] = []
        price_date: Optional[datetime] = None

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                
                # Extract date from first page
                if price_date is None and text:
                    price_date = self._extract_date(text)

                # Get all category headers with positions
                category_headers = self._extract_category_headers(page)
                
                # Parse products from page with category assignment
                page_products = self._parse_page_products(page, category_headers)
                products.extend(page_products)

        return ParsedPriceList(
            date=price_date or datetime.now(),
            products=products,
            source_file=file_path.name,
        )

    def _extract_date(self, text: str) -> Optional[datetime]:
        """Extract date from price list header."""
        match = self.DATE_PATTERN.search(text)
        if match:
            day, month, year = match.groups()
            return datetime(int(year), int(month), int(day))
        return None

    def _extract_category_headers(self, page) -> list[CategoryHeader]:
        """
        Extract all category headers from page with their positions.
        Returns list of CategoryHeader objects sorted by position.
        """
        words = page.extract_words()
        headers = []
        
        # Group words by approximate position for multi-word categories
        # Build a map of words by their approximate y-coordinate
        words_by_y = {}
        for w in words:
            y_key = int(w['top'] / 10) * 10  # Group by 10-pixel bands
            if y_key not in words_by_y:
                words_by_y[y_key] = []
            words_by_y[y_key].append(w)
        
        processed_positions = set()  # Avoid duplicates
        
        for w in words:
            text_upper = w['text'].upper()
            x, y = w['x0'], w['top']
            
            # Skip if we already processed this approximate position
            pos_key = (int(x / 100), int(y / 20))
            if pos_key in processed_positions:
                continue
            
            category = None
            form = None
            
            # Check for compound categories first (КОМПОТНЫЕ СМЕСИ, ОВОЩНЫЕ СМЕСИ)
            for compound in self.COMPOUND_CATEGORIES:
                first_word = compound.split()[0]
                if text_upper == first_word:
                    # Look for "СМЕСИ" nearby
                    y_key = int(y / 10) * 10
                    for check_y in [y_key, y_key + 10, y_key - 10]:
                        if check_y in words_by_y:
                            for nearby_w in words_by_y[check_y]:
                                if nearby_w['text'].upper() == 'СМЕСИ' and abs(nearby_w['x0'] - x) < 150:
                                    category = compound.replace('КОМПОТНЫЕ', 'Компотные').replace('ОВОЩНЫЕ', 'Овощные').replace('СМЕСИ', 'смеси')
                                    break
                        if category:
                            break
            
            # Check for simple categories
            if not category:
                for cat_keyword in self.CATEGORY_KEYWORDS:
                    if text_upper == cat_keyword:
                        category = cat_keyword.capitalize()
                        break
            
            if category:
                # Look for form (ЗАМОРОЖЕННЫЕ/СУШЕНЫЕ) nearby
                # Form should be to the right of category or very close
                form = None
                y_key = int(y / 10) * 10
                
                best_form = None
                best_distance = float('inf')
                
                for check_y in [y_key, y_key + 10, y_key - 10, y_key + 20]:
                    if check_y in words_by_y:
                        for nearby_w in words_by_y[check_y]:
                            nearby_text = nearby_w['text'].upper()
                            # Check for form keywords
                            for form_kw in self.FORM_KEYWORDS:
                                if form_kw in nearby_text or nearby_text in form_kw:
                                    nearby_x = nearby_w['x0']
                                    # Form should be to the right of category or very close
                                    # And in the same column (not too far left)
                                    x_diff = nearby_x - x
                                    
                                    # Accept if: to the right and within 150px, or very close (within 50px either side)
                                    if (-50 < x_diff < 150):
                                        distance = abs(x_diff) + abs(nearby_w['top'] - y)
                                        if distance < best_distance:
                                            best_distance = distance
                                            best_form = 'Сушёные' if 'СУШ' in nearby_text else 'Замороженные'
                
                form = best_form
                
                if form:
                    headers.append(CategoryHeader(
                        category=category,
                        form=form,
                        x=x,
                        y=y
                    ))
                    processed_positions.add(pos_key)
        
        # Sort by y first (top to bottom), then by x (left to right)
        headers.sort(key=lambda h: (h.y, h.x))
        
        return headers

    def _parse_page_products(self, page, category_headers: list[CategoryHeader]) -> list[ParsedProduct]:
        """
        Parse all products from page, assigning categories based on position.
        """
        products = []
        
        # Define column boundaries (left column: x < 300, right column: x >= 300)
        COLUMN_SPLIT = 300
        
        # Separate headers by column
        left_headers = [h for h in category_headers if h.x < COLUMN_SPLIT]
        right_headers = [h for h in category_headers if h.x >= COLUMN_SPLIT]
        
        # Extract tables
        tables = page.find_tables()
        
        for table in tables:
            bbox = table.bbox  # (x0, y0, x1, y1)
            table_x = (bbox[0] + bbox[2]) / 2  # Center x of table
            is_left_column = table_x < COLUMN_SPLIT
            
            # Get relevant headers for this column
            relevant_headers = left_headers if is_left_column else right_headers
            
            # Parse table with row positions
            table_data = table.extract()
            
            # Get row positions from table cells
            cells = page.crop(bbox).extract_words()
            
            # Build a map of y-coordinates for each row
            # Using the table data and estimating row heights
            table_height = bbox[3] - bbox[1]
            num_rows = len(table_data)
            row_height = table_height / max(num_rows, 1)
            
            for row_idx, row in enumerate(table_data):
                # Estimate y position of this row
                row_y = bbox[1] + (row_idx * row_height)
                
                # Find the category for this row
                category, form = self._find_category_for_position(
                    row_y, bbox[0], relevant_headers, is_left_column
                )
                
                # Try to parse product from row
                product = self._parse_row(row, category, form)
                if product:
                    products.append(product)
        
        return products

    def _find_category_for_position(
        self, 
        row_y: float, 
        row_x: float,
        headers: list[CategoryHeader],
        is_left_column: bool
    ) -> tuple[str, str]:
        """
        Find the category for a given row position.
        Returns (category, form) tuple.
        """
        # Default fallback
        default = ("Прочее", "Замороженные")
        
        if not headers:
            return default
        
        # Find the header that is above this row and closest to it
        best_header = None
        for header in headers:
            # Header must be above the row (header.y < row_y)
            if header.y < row_y:
                if best_header is None or header.y > best_header.y:
                    best_header = header
        
        if best_header:
            return (best_header.category, best_header.form)
        
        return default

    def _parse_row(self, row: list, category: str, form: str) -> Optional[ParsedProduct]:
        """Parse a single row into a product."""
        if not row or len(row) < 2:
            return None
        
        # Find name (first non-empty cell that's not a header)
        name = None
        for cell in row[:2]:
            if cell:
                cleaned = self._clean_text(cell)
                if cleaned and cleaned.lower() not in ['наименование', 'цена', 'за 1 кг', '']:
                    # Skip if looks like a category header
                    upper = cleaned.upper()
                    is_header = False
                    for kw in self.CATEGORY_KEYWORDS + ['КОМПОТНЫЕ', 'ОВОЩНЫЕ', 'СМЕСИ'] + self.FORM_KEYWORDS:
                        if upper == kw:
                            is_header = True
                            break
                    if not is_header:
                        name = cleaned
                        break
        
        if not name:
            return None
        
        # Find price
        price = None
        is_available = False
        
        for cell in row[2:]:
            if cell:
                cell_str = str(cell)
                price, is_available = self._parse_price(cell_str)
                if price is not None or "- ₽" in cell_str or cell_str.strip() == "-":
                    break
        
        # Extract country from name
        origin_country = self._extract_country(name)
        
        # Clean name (remove country)
        clean_name = self.COUNTRY_PATTERN.sub("", name).strip()
        
        # Skip empty names
        if not clean_name:
            return None
        
        return ParsedProduct(
            name=clean_name,
            category=category,
            product_form=form,
            price=price,
            is_available=is_available,
            origin_country=origin_country,
        )

    def _parse_price(self, price_str: str) -> tuple[Optional[float], bool]:
        """Parse price string. Returns (price, is_available)."""
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

    def _extract_country(self, name: str) -> Optional[str]:
        """Extract country from product name."""
        match = self.COUNTRY_PATTERN.search(name)
        if match:
            return match.group(1)
        return None

    def _clean_text(self, text: Optional[str]) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        cleaned = re.sub(r"\s+", " ", str(text)).strip()
        return cleaned


def parse_price_list(file_path: str | Path) -> ParsedPriceList:
    """Convenience function to parse a price list file."""
    parser = PDFPriceParser()
    return parser.parse(file_path)