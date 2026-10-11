
from decimal import Decimal, InvalidOperation


def reconcile_budget(transactions, stated_grand_total, stated_category_totals):
    """Compare transaction amounts with declared budget totals."""
    findings = []

    try:
        stated_grand_total = Decimal(str(stated_grand_total))
        if not stated_grand_total.is_finite():
            raise ValueError("Grand total must be a finite number.")
    except (InvalidOperation, ValueError):
        return [{
            "type": "invalid_budget_total",
            "severity": "error",
            "message": "The stated grand total is invalid."
        }]

    actual_total = Decimal("0")
    actual_categories = {}

    for transaction in transactions:
        try:
            amount = Decimal(str(transaction.get("amount", 0)))
            if not amount.is_finite():
                raise ValueError("Amount must be finite.")
        except (InvalidOperation, ValueError):
            findings.append({
                "type": "invalid_amount",
                "severity": "error",
                "message": (
                    "Invalid amount in transaction "
                    f"{transaction.get('transaction_id', 'UNKNOWN')}."
                )
            })
            continue

        actual_total += amount
        category = str(transaction.get("category") or "").strip()

        if category:
            actual_categories[category] = (
                actual_categories.get(category, Decimal("0")) + amount
            )

    difference = actual_total - stated_grand_total

    if difference != 0:
        findings.append({
            "type": "grand_total_discrepancy",
            "severity": "review",
            "stated_total": str(stated_grand_total),
            "actual_total": str(actual_total),
            "difference": str(difference),
            "message": "Transaction total differs from the stated budget total."
        })

    for category, stated_value in stated_category_totals.items():
        try:
            stated_value = Decimal(str(stated_value))
            if not stated_value.is_finite():
                raise ValueError("Category total must be finite.")
        except (InvalidOperation, ValueError):
            findings.append({
                "type": "invalid_category_total",
                "severity": "error",
                "category": category,
                "message": f"Invalid stated total for category: {category}."
            })
            continue

        actual_value = actual_categories.get(category, Decimal("0"))

        if actual_value != stated_value:
            findings.append({
                "type": "category_discrepancy",
                "severity": "review",
                "category": category,
                "stated_total": str(stated_value),
                "actual_total": str(actual_value),
                "difference": str(actual_value - stated_value),
                "message": f"Budget total differs for category: {category}."
            })

    return findings
