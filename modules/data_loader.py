

"""Load standard transaction CSVs and public expenditure datasets."""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED_COLUMNS = {
    "transaction_id",
    "date",
    "description",
    "category",
    "amount",
    "reference",
}

# Headers used by the WorldExpenditures.csv dataset.
EXPENDITURE_COLUMNS = {
    "year",
    "country",
    "sector",
    "expenditure(million usd)",
    "gdp(%)",
}


def _clean_header(name: str) -> str:
    """Normalize column names for reliable format detection."""
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def load_transactions(uploaded_file) -> list[dict]:
    """Load standard transactions or public expenditure records.

    Accepts a filesystem path, bytes, or a readable uploaded file object.
    The source file is never modified.
    """
    if isinstance(uploaded_file, (str, Path)):
        with open(
            uploaded_file, "r", encoding="utf-8-sig", newline=""
        ) as file:
            return _parse_csv(file)

    if isinstance(uploaded_file, bytes):
        uploaded_file = io.BytesIO(uploaded_file)

    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    if isinstance(uploaded_file, io.TextIOBase):
        return _parse_csv(uploaded_file)

    if hasattr(uploaded_file, "read"):
        content = uploaded_file.read()

        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")

        return _parse_csv(io.StringIO(content))

    raise TypeError("Expected a CSV path or readable file object.")


def _parse_csv(file) -> list[dict]:
    """Detect the CSV format and parse it into internal records."""
    reader = csv.DictReader(file)

    if not reader.fieldnames:
        raise ValueError("The CSV file is empty or has no header.")

    # Strip whitespace and a possible UTF-8 BOM from headers.
    reader.fieldnames = [
        name.strip().lstrip("\ufeff") if name else ""
        for name in reader.fieldnames
    ]

    header_map = {
        _clean_header(name): name
        for name in reader.fieldnames
        if name
    }

    # Prefer the standard transaction format when its required columns exist.
    normalized_headers = set(header_map)

    if REQUIRED_COLUMNS.issubset(normalized_headers):
        return _parse_standard_transactions(reader)

    if EXPENDITURE_COLUMNS.issubset(normalized_headers):
        return _parse_public_expenditure(reader, header_map)

    missing = REQUIRED_COLUMNS - normalized_headers

    raise ValueError(
        "Unsupported CSV format. Expected either standard transaction "
        "columns (transaction_id, date, description, category, amount, "
        "reference) or public expenditure columns "
        "(Year, Country, Sector, Expenditure(million USD), GDP(%)). "
        "Missing standard columns: "
        + ", ".join(sorted(missing))
    )


def _parse_standard_transactions(reader) -> list[dict]:
    """Parse existing BudgetClear transaction CSVs."""
    transactions = []

    for row in reader:
        transaction = {
            key.strip(): (
                value.strip() if value is not None else ""
            )
            for key, value in row.items()
            if key is not None
        }

        amount = transaction.get("amount", "")

        try:
            transaction["amount"] = Decimal(amount.replace(",", ""))
        except (InvalidOperation, AttributeError):
            # Preserve invalid input for the validation module.
            pass

        transactions.append(transaction)

    return transactions


def _parse_public_expenditure(reader, header_map) -> list[dict]:
    """Convert country-year-sector expenditure records into app records.

    The original expenditure unit is million USD, not INR.
    Missing values remain missing so validation can report them.
    """
    year_col = header_map["year"]
    country_col = header_map["country"]
    sector_col = header_map["sector"]
    expenditure_col = header_map["expenditure(million usd)"]
    gdp_col = header_map["gdp(%)"]

    transactions = []

    for row_number, row in enumerate(reader, start=1):
        year = _clean_value(row.get(year_col))
        country = _clean_value(row.get(country_col))
        sector = _clean_value(row.get(sector_col))
        raw_amount = _clean_value(row.get(expenditure_col))
        raw_gdp = _clean_value(row.get(gdp_col))

        # Use January 1 as a representative date for year-level data.
        # This does not imply that a transaction occurred on that day.
        date_value = f"{year}-01-01" if year else ""

        transaction = {
            "transaction_id": f"EXP-{row_number:06d}",
            "date": date_value,
            "description": (
                f"{country} - {sector}"
                if country and sector
                else country or sector
            ),
            "category": sector,
            "amount": _parse_decimal_or_preserve(raw_amount),
            "reference": f"WORLD-EXP-{row_number:06d}",
            "country": country,
            "year": year,
            "gdp_percent": _parse_decimal_or_preserve(raw_gdp),
            "amount_unit": "million USD",
            "dataset_type": "public_expenditure",
        }

        transactions.append(transaction)

    return transactions


def _clean_value(value) -> str:
    """Convert a CSV value to a stripped string."""
    if value is None:
        return ""

    return str(value).strip()


def _parse_decimal_or_preserve(value: str):
    """Convert valid numbers to Decimal; preserve blanks and invalid input."""
    if not value:
        return ""

    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return value
