"""
Price list parsers for different file formats.
"""

from pathlib import Path

from src.data.parsers.pdf_parser import (
    PDFPriceParser,
    ParsedPriceList,
    ParsedProduct,
    parse_price_list,
)
from src.data.parsers.xlsx_parser import XLSXPriceParser, parse_xlsx_price_list


def parse_file(file_path: str | Path) -> ParsedPriceList:
    """
    Parse price list file based on extension.

    Args:
        file_path: Path to PDF or XLSX file

    Returns:
        ParsedPriceList with extracted products

    Raises:
        ValueError: If file format is not supported
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return parse_price_list(file_path)
    elif suffix in [".xlsx", ".xls"]:
        return parse_xlsx_price_list(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


__all__ = [
    "PDFPriceParser",
    "XLSXPriceParser",
    "ParsedPriceList",
    "ParsedProduct",
    "parse_file",
    "parse_price_list",
    "parse_xlsx_price_list",
]
