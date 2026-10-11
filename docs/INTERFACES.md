# BudgetClear Shared Interfaces

## 1. Data loading
File: modules/data_loader.py
Function: load_transactions(uploaded_file) -> list[dict]

## 2. Validation
File: modules/validation.py
Function: validate_transactions(transactions) -> dict

Expected keys:
- valid
- errors
- warnings
- normalized_transactions

## 3. Duplicate detection
File: modules/duplicate_detection.py
Function: detect_duplicates(transactions) -> list[dict]

## 4. Reconciliation
File: modules/reconciliation.py
Function: reconcile_budget(
    transactions,
    stated_grand_total,
    stated_category_totals
) -> list[dict]

Use exact Decimal arithmetic. Difference means calculated total minus stated total.

## 5. AI assistance
File: modules/ai_assist.py
Functions:
- suggest_categories(transactions) -> list[dict]
- suggest_anomalies(transactions) -> list[dict]

AI suggestions must never change verified totals or silently fill missing categories.

## 6. Dashboard
File: app.py

Execution order:
1. Load transactions
2. Validate and show errors/warnings
3. Reconcile budget
4. Detect duplicate candidates
5. Generate AI suggestions
6. Allow human review
7. Export the report

## Shared rules
- Use fictional data only.
- Use Decimal, never float, for money calculations.
- Preserve the original input.
- Keep verified findings separate from AI suggestions.
- Every finding must include supporting evidence.
- An anomaly flag is not proof of wrongdoing.
