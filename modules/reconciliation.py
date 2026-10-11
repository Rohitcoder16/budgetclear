
from decimal import Decimal, InvalidOperation
from itertools import count

TWO_PLACES = Decimal("0.01")


def to_decimal(value):
    """Return a finite Decimal, or None if missing or invalid."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None

    return number if number.is_finite() else None


def money(value):
    """Format monetary values with two decimal places."""
    rounded = value.quantize(TWO_PLACES)
    return str(rounded) if rounded == value else format(value, "f")


def make_finding(number, finding_type, title, severity, message,
                 evidence_ids, difference=None):
    return {
        "finding_id": f"F-{number:03d}",
        "finding_type": finding_type,
        "title": title,
        "severity": severity,
        "source": "rule_engine",
        "message": message,
        "evidence_transaction_ids": list(evidence_ids),
        "amount_difference": (
            None if difference is None else money(difference)
        ),
        "confidence": None,
        "requires_human_review": True,
    }


def reconcile_budget(transactions, stated_grand_total, stated_category_totals):
    """Compare transaction totals with stated budget totals."""
    findings = []
    ids = count(1)

    valid_rows = []
    invalid_ids = []

    # Validate transaction amounts.
    for transaction in transactions:
        tid = transaction.get("transaction_id")
        amount = to_decimal(transaction.get("amount"))

        if amount is None:
            invalid_ids.append(tid)
            findings.append(make_finding(
                next(ids),
                "invalid_amount",
                "Invalid or missing amount",
                "medium",
                f"Transaction {tid} has an invalid or missing amount "
                "and was excluded from the totals.",
                [tid],
            ))
        else:
            valid_rows.append((transaction, amount))

    calculated_total = sum(
        (amount for _, amount in valid_rows), Decimal("0")
    )

    # Compare grand totals.
    stated_total = to_decimal(stated_grand_total)

    if stated_total is None:
        findings.append(make_finding(
            next(ids),
            "invalid_budget_total",
            "Invalid stated grand total",
            "high",
            "The stated grand total is missing or invalid, so it cannot "
            "be compared with the calculated transaction total.",
            [],
        ))
    else:
        difference = calculated_total - stated_total

        if difference != 0:
            note = ""
            if invalid_ids:
                note = (
                    f" {len(invalid_ids)} transaction(s) with invalid "
                    "amounts were excluded."
                )

            findings.append(make_finding(
                next(ids),
                "grand_total_mismatch",
                "Grand total mismatch",
                "high",
                f"Transactions total {money(calculated_total)}, but the "
                f"stated total is {money(stated_total)}.{note}",
                [t.get("transaction_id") for t, _ in valid_rows],
                difference,
            ))

    # Group valid transactions by category, ignoring letter case.
    by_category = {}
    uncategorized = []

    for transaction, amount in valid_rows:
        category = str(transaction.get("category") or "").strip()

        if not category:
            uncategorized.append(
                (transaction.get("transaction_id"), amount)
            )
        else:
            by_category.setdefault(category.casefold(), []).append(
                (transaction.get("transaction_id"), amount)
            )

    # Compare category totals.
    for category, stated_value in (stated_category_totals or {}).items():
        stated_category = to_decimal(stated_value)

        if stated_category is None:
            findings.append(make_finding(
                next(ids),
                "invalid_category_total",
                f"Invalid category total: {category}",
                "high",
                f"The stated total for category '{category}' is missing "
                "or invalid, so it cannot be compared.",
                [],
            ))
            continue

        rows = by_category.get(category.strip().casefold(), [])
        calculated = sum(
            (amount for _, amount in rows), Decimal("0")
        )
        difference = calculated - stated_category

        if difference != 0:
            findings.append(make_finding(
                next(ids),
                "category_total_mismatch",
                f"Category total mismatch: {category}",
                "high",
                f"Transactions in '{category}' total {money(calculated)}, "
                f"but the stated total is {money(stated_category)}.",
                [transaction_id for transaction_id, _ in rows],
                difference,
            ))

    # Report transactions that have no category.
    if uncategorized:
        uncategorized_total = sum(
            (amount for _, amount in uncategorized), Decimal("0")
        )

        findings.append(make_finding(
            next(ids),
            "uncategorized_rows",
            "Transactions without a category",
            "low",
            f"{len(uncategorized)} transaction(s), totaling "
            f"{money(uncategorized_total)}, have no category. They count "
            "toward the grand total but not toward any category total.",
            [transaction_id for transaction_id, _ in uncategorized],
        ))

    return findings
