from modules.duplicate_detection import detect_duplicates


def test_exact_duplicate_is_detected():
    rows = [
        {
            "transaction_id": "TXN-001",
            "date": "2026-10-08",
            "amount": "100",
            "reference": "INV-001",
            "description": "Office supplies",
        },
        {
            "transaction_id": "TXN-002",
            "date": "2026-10-08",
            "amount": "100",
            "reference": "INV-001",
            "description": "Office supplies",
        },
    ]

    findings = detect_duplicates(rows)

    assert len(findings) == 1
    assert findings[0]["type"] == "exact_duplicate_candidate"
    assert findings[0]["evidence_ids"] == ["TXN-001", "TXN-002"]