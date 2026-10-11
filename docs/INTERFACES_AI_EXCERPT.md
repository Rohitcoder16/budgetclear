# BudgetClear Shared Interfaces

This file documents the team's agreed module signatures. Do not change a shared function name or return shape without telling the team.

## AI assistance (Member 3)
- `modules/ai_assist.py`
- `suggest_categories(transactions) -> list[dict]`
- `suggest_anomalies(transactions) -> list[dict]`

Category suggestion keys:
`transaction_id`, `suggested_category`, `confidence` (0 to 1), `reason`, `source`, `review_status`.

Anomaly suggestion keys:
`transaction_id`, `severity`, `message`, `reason`, `source`, `evidence_transaction_ids`, `check_performed`, `review_status`.

AI suggestions are separate from verified findings. Missing categories stay missing until accepted by a human. An anomaly is not proof of wrongdoing.
