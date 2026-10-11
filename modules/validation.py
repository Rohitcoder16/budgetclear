
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re


def validate_transactions(transactions):
    valid = []
    errors = []
    warnings = []
    normalized = []

    for original in transactions:
        row = dict(original)
        txid = row.get("transaction_id", "UNKNOWN")
        row_errors = []
        row_warnings = []

        # Validate date
        date_value = str(row.get("date", "")).strip()
        parsed_date = None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed_date = datetime.strptime(date_value, fmt)
                break
            except ValueError:
                continue

        if parsed_date is None:
            row_errors.append("Invalid or missing date.")
        else:
            row["date"] = parsed_date.strftime("%Y-%m-%d")

        # Validate amount using Decimal, never float
        amount_value = str(row.get("amount", "")).strip()
        amount_value = re.sub(r"(?i)\b(rs\.?|inr|₹)\s*", "", amount_value)
        amount_value = amount_value.replace(",", "").replace(" ", "")

        try:
            amount = Decimal(amount_value)
            if not amount.is_finite():
                raise InvalidOperation
            row["amount"] = format(amount, "f")
        except (InvalidOperation, ValueError):
            row_errors.append("Invalid or missing amount.")

        # Missing category stays blank
        row["category"] = str(row.get("category") or "").strip()
        if not row["category"]:
            row_warnings.append("Category is missing.")

        if row_errors:
            errors.append({
                "transaction_id": txid,
                "messages": row_errors,
            })
        else:
            valid.append(row)

        if row_warnings:
            warnings.append({
                "transaction_id": txid,
                "messages": row_warnings,
            })

        normalized.append(row)

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "normalized_transactions": normalized,
    }
