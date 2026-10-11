
"""Load CSV spending records without modifying the source file."""

import csv
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


def load_transactions(uploaded_file) -> list[dict]:
    """Load CSV records from a path or uploaded file-like object."""
    if isinstance(uploaded_file, (str, Path)):
        with open(uploaded_file, "r", encoding="utf-8-sig", newline="") as file:
            return _parse_csv(file)

    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    import io

    if isinstance(uploaded_file, bytes):
        uploaded_file = io.BytesIO(uploaded_file)

    if isinstance(uploaded_file, io.TextIOBase):
        return _parse_csv(uploaded_file)

    if hasattr(uploaded_file, "read"):
        content = uploaded_file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        return _parse_csv(io.StringIO(content))

    raise TypeError("Expected a CSV path or readable file object.")


def _parse_csv(file) -> list[dict]:
    reader = csv.DictReader(file)

    if not reader.fieldnames:
        raise ValueError("The CSV file is empty or has no header.")

    reader.fieldnames = [name.strip() for name in reader.fieldnames]
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    transactions = []
    for row in reader:
        transaction = {
            key: (value.strip() if value is not None else "")
            for key, value in row.items()
            if key is not None
        }

        amount = transaction.get("amount", "")
        try:
            transaction["amount"] = Decimal(amount.replace(",", ""))
        except (InvalidOperation, AttributeError):
            # Preserve the invalid input for validation to report.
            pass

        transactions.append(transaction)

    return transactions
