from copy import deepcopy
from decimal import Decimal

from modules.ai_assist import suggest_categories, suggest_anomalies


def test_category_suggestion_does_not_mutate_or_fill_input():
    rows = [{
        "transaction_id": "TXN-001",
        "description": "Purchase printer paper and office stationery",
        "category": "",
        "amount": "1200.00",
    }]
    original = deepcopy(rows)
    suggestions = suggest_categories(rows)
    assert rows == original
    assert len(suggestions) == 1
    item = suggestions[0]
    assert item["transaction_id"] == "TXN-001"
    assert 0 <= item["confidence"] <= 1
    assert item["reason"]
    assert item["source"] in {"ai_model", "fallback_heuristic"}
    assert item["review_status"] == "needs_review"
    assert rows[0]["category"] == ""


def test_existing_category_is_not_suggested_or_changed():
    rows = [{
        "transaction_id": "TXN-002",
        "description": "Electricity bill",
        "category": "Utilities",
        "amount": "900.00",
    }]
    original = deepcopy(rows)
    assert suggest_categories(rows) == []
    assert rows == original


def test_missing_description_returns_reviewable_item():
    rows = [{
        "transaction_id": "TXN-003",
        "description": "",
        "category": "",
        "amount": "20.00",
    }]
    item = suggest_categories(rows)[0]
    assert item["suggested_category"] is None
    assert item["confidence"] == 0.0
    assert item["reason"]
    assert item["source"] == "fallback_heuristic"


def test_anomaly_finding_uses_decimal_and_contains_evidence():
    rows = [
        {"transaction_id": "TXN-101", "category": "Office Supplies", "amount": "100.00"},
        {"transaction_id": "TXN-102", "category": "Office Supplies", "amount": "110.00"},
        {"transaction_id": "TXN-103", "category": "Office Supplies", "amount": "95.00"},
        {"transaction_id": "TXN-104", "category": "Office Supplies", "amount": "10000.00"},
    ]
    original = deepcopy(rows)
    findings = suggest_anomalies(rows)
    assert rows == original
    item = next(f for f in findings if f["transaction_id"] == "TXN-104")
    assert item["source"] == "fallback_heuristic"
    assert item["review_status"] == "needs_review"
    assert item["check_performed"]
    assert item["reason"]
    assert "TXN-104" in item["evidence_transaction_ids"]
    assert len(item["evidence_transaction_ids"]) == 4


def test_anomaly_skips_missing_category_and_invalid_amount():
    rows = [
        {"transaction_id": "TXN-1", "category": "", "amount": "100"},
        {"transaction_id": "TXN-2", "category": "Travel", "amount": "not-money"},
        {"transaction_id": "TXN-3", "category": "Travel", "amount": "100"},
    ]
    assert suggest_anomalies(rows) == []


def test_ollama_failure_falls_back(monkeypatch):
    import modules.ai_assist as module
    monkeypatch.setenv("BUDGETCLEAR_USE_OLLAMA", "1")

    def fail():
        raise OSError("Ollama unavailable")

    monkeypatch.setattr(module, "_ollama_category", lambda description: fail())
    rows = [{
        "transaction_id": "TXN-009",
        "description": "Taxi fare for official travel",
        "category": "",
        "amount": "500.00",
    }]
    item = suggest_categories(rows)[0]
    assert item["source"] == "fallback_heuristic"
    assert item["transaction_id"] == "TXN-009"
    assert item["reason"]
