from decimal import Decimal, InvalidOperation
from itertools import count

TWO_PLACES = Decimal("0.01")


def to_decimal(value):
    """Return a finite Decimal, or None if the value is missing or invalid."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():          # rejects NaN and Infinity
        return None
    return number


def money(value):
    """Format a Decimal as text with 2 decimal places, without rounding anything away."""
    two = value.quantize(TWO_PLACES)
    return str(two) if two == value else format(value, "f")


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
        "amount_difference": None if difference is None else money(difference),
        "confidence": None,
        "requires_human_review": True,
    }


def reconcile_budget(transactions, stated_grand_total, stated_category_totals):
    findings = []
    ids = count(1)                       # F-001, F-002, ...

    valid_rows = []                      # (transaction, Decimal amount)
    invalid_ids = []
    for t in transactions:
        tid = t.get("transaction_id")
        amount = to_decimal(t.get("amount"))
        if amount is None:
            invalid_ids.append(tid)
            findings.append(make_finding(
                next(ids), "invalid_amount", "Invalid or missing amount", "medium",
                f"Row {tid} has an amount that cannot be read, so it is left out of the totals.",
                [tid]))
        else:
            valid_rows.append((t, amount))

    calculated_total = sum((a for _, a in valid_rows), Decimal("0"))
    stated_total = to_decimal(stated_grand_total)

    if stated_total is not None:
        # Sign rule (see INTERFACES.md): difference = calculated total minus stated total
        difference = calculated_total - stated_total
        if difference != 0:
            note = ""
            if invalid_ids:
                note = f" ({len(invalid_ids)} row(s) with unreadable amounts were left out.)"
            findings.append(make_finding(
                next(ids), "grand_total_mismatch", "Grand total mismatch", "high",
                f"Line items add up to {money(calculated_total)} but the stated total is "
                f"{money(stated_total)}.{note}",
                [t.get("transaction_id") for t, _ in valid_rows], difference))

    by_category = {}                     # lowercase name -> list of (id, amount)
    uncategorized = []
    for t, amount in valid_rows:
        name = (t.get("category") or "").strip()
        if name == "":
            uncategorized.append((t.get("transaction_id"), amount))
        else:
            by_category.setdefault(name.casefold(), []).append((t.get("transaction_id"), amount))

    for name, stated_value in (stated_category_totals or {}).items():
        stated_cat = to_decimal(stated_value)
        if stated_cat is None:
            continue
        rows = by_category.get(name.strip().casefold(), [])
        calculated = sum((a for _, a in rows), Decimal("0"))
        diff = calculated - stated_cat
        if diff != 0:
            findings.append(make_finding(
                next(ids), "category_total_mismatch", f"Category total mismatch: {name}", "high",
                f"{name} rows add up to {money(calculated)} but the stated total is {money(stated_cat)}.",
                [i for i, _ in rows], diff))

    if uncategorized:
        total = sum((a for _, a in uncategorized), Decimal("0"))
        findings.append(make_finding(
            next(ids), "uncategorized_rows", "Rows without a category", "low",
            f"{len(uncategorized)} row(s) have no category (together {money(total)}). "
            "They count in the grand total but in no category.",
            [i for i, _ in uncategorized]))

    return findings