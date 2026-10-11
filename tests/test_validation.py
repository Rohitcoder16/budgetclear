from modules.validation import validate_transactions


def test_valid_amount_and_date():
    rows = [{
        "transaction_id": "TXN-001",
        "date": "08/10/2026",
        "description": "Office supplies",
        "category": "Supplies",
        "amount": "Rs. 1,20,000",
        "reference": "INV-001",
    }]

    result = validate_transactions(rows)

    assert result["valid"][0]["date"] == "2026-10-08"
    assert result["valid"][0]["amount"] == "120000"
    assert result["errors"] == []


def test_missing_category_stays_blank():
    rows = [{
        "transaction_id": "TXN-002",
        "date": "2026-10-08",
        "description": "Expense",
        "category": "",
        "amount": "100",
        "reference": "INV-002",
    }]

    result = validate_transactions(rows)

    assert result["normalized_transactions"][0]["category"] == ""
    assert len(result["warnings"]) == 1


def test_invalid_amount_is_reported():
    rows = [{
        "transaction_id": "TXN-003",
        "date": "2026-10-08",
        "description": "Expense",
        "category": "Other",
        "amount": "abc",
        "reference": "INV-003",
    }]

    result = validate_transactions(rows)

    assert len(result["errors"]) == 1
    assert result["valid"] == []