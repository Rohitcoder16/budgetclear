import copy
from modules.reconciliation import reconcile_budget


def rows():
    return [
        {"transaction_id": "TXN-001", "category": "Equipment", "amount": "100.00"},
        {"transaction_id": "TXN-002", "category": "Equipment", "amount": "50.00"},
        {"transaction_id": "TXN-003", "category": "Travel", "amount": "30.00"},
    ]


def types(findings):
    return [f["finding_type"] for f in findings]


# Test 1: everything matches, so there should be no findings
def test_matching_totals_give_no_findings():
    assert reconcile_budget(rows(), "180.00", {"Equipment": "150.00", "Travel": "30.00"}) == []


# Test 2: grand total is off by 10.00
def test_grand_total_off_by_ten():
    result = reconcile_budget(rows(), "170.00", {})
    assert types(result) == ["grand_total_mismatch"]
    assert result[0]["amount_difference"] == "10.00"      # calculated minus stated


# Test 3: categories are wrong even though the grand total matches
def test_category_mismatch_even_when_grand_total_matches():
    result = reconcile_budget(rows(), "180.00", {"Equipment": "140.00", "Travel": "40.00"})
    assert types(result) == ["category_total_mismatch", "category_total_mismatch"]
    assert result[0]["amount_difference"] == "10.00"
    assert result[1]["amount_difference"] == "-10.00"


# Test 4: a row with no category is reported, never guessed into a category
def test_missing_category_is_not_guessed():
    data = rows() + [{"transaction_id": "TXN-004", "category": None, "amount": "20.00"}]
    result = reconcile_budget(data, "200.00", {"Equipment": "150.00"})
    assert types(result) == ["uncategorized_rows"]
    assert result[0]["evidence_transaction_ids"] == ["TXN-004"]


# Test 5: an unreadable amount is reported, not counted as zero
def test_invalid_amount_is_reported_not_treated_as_zero():
    data = rows() + [{"transaction_id": "TXN-004", "category": "Travel", "amount": "abc"}]
    result = reconcile_budget(data, "180.00", {})
    assert types(result) == ["invalid_amount"]            # 180.00 still matches the valid rows


# Test 6: empty list behaves predictably
def test_empty_list():
    assert reconcile_budget([], "0.00", {}) == []
    assert reconcile_budget([], "10.00", {})[0]["amount_difference"] == "-10.00"


# Test 7: the function must not change the data it receives
def test_input_is_not_changed():
    data = rows()
    before = copy.deepcopy(data)
    reconcile_budget(data, "170.00", {"Equipment": "150.00"})
    assert data == before


# Test 8: a blank category that pandas turns into NaN is still treated as missing
def test_nan_category_is_treated_as_missing():
    data = rows() + [{"transaction_id": "TXN-004", "category": float("nan"), "amount": "20.00"}]
    result = reconcile_budget(data, "200.00", {"Equipment": "150.00"})
    assert types(result) == ["uncategorized_rows"]