
from decimal import Decimal, InvalidOperation
from itertools import count

TWO_PLACES = Decimal("0.01")


def to_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def money(value):
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
    findings = []
    ids = count(1)
    valid_rows = []
    invalid_ids = []

    for transaction in transactions:
        tid = transaction.get("transaction_id")
        amount = to_decimal(transaction.get("amount"))

        if amount is None:
            invalid_ids.append(tid)
            findings.append(make_finding(
                next(ids), "invalid_amount", "Invalid or missing amount",
                "medium", f"Transaction {tid} has an invalid amount.",
                [tid]))
        else:
            valid_rows.append((transaction, amount))

    calculated_total = sum(
        (amount for _, amount in valid_rows), Decimal("0")
    )
    stated_total = to_decimal(stated_grand_total)

    if stated_total is None:
        findings.append(make_finding(
            next(ids), "invalid_budget_total", "Invalid stated grand total",
            "high", "The stated grand total is missing or invalid.", []))
    else:
        # Sign rule: difference = calculated total minus stated total
        difference = calculated_total - stated_total
        if difference != 0:
            findings.append(make_finding(
                next(ids), "grand_total_mismatch", "Grand total mismatch",
                "high",
                f"Transactions total {money(calculated_total)}, but the "
                f"stated total is {money(stated_total)}.",
                [t.get("transaction_id") for t, _ in valid_rows],
                difference))

    by_category = {}
    uncategorized = []

    for transaction, amount in valid_rows:
        raw = transaction.get("category")
        category = "" if raw is None else str(raw).strip()
        if category.casefold() in ("nan", "none", "null"):
            category = ""

        if category:
            by_category.setdefault(category.casefold(), []).append(
                (transaction.get("transaction_id"), amount))
        else:
            uncategorized.append(
                (transaction.get("transaction_id"), amount))

    for category, stated_value in (stated_category_totals or {}).items():
        stated_category = to_decimal(stated_value)

        if stated_category is None:
            findings.append(make_finding(
                next(ids), "invalid_category_total",
                f"Invalid category total: {category}", "high",
                f"The stated total for '{category}' is missing or invalid.",
                []))
            continue

        rows = by_category.get(category.strip().casefold(), [])
        calculated = sum((amount for _, amount in rows), Decimal("0"))
        difference = calculated - stated_category

        if difference != 0:
            findings.append(make_finding(
                next(ids), "category_total_mismatch",
                f"Category total mismatch: {category}", "high",
                f"Transactions in '{category}' total {money(calculated)}, "
                f"but the stated total is {money(stated_category)}.",
                [tid for tid, _ in rows], difference))

    if uncategorized:
        total = sum((amount for _, amount in uncategorized), Decimal("0"))
        findings.append(make_finding(
            next(ids), "uncategorized_rows", "Transactions without a category",
            "low",
            f"{len(uncategorized)} transaction(s), totaling {money(total)}, "
            "have no category.",
            [tid for tid, _ in uncategorized]))

    return findings