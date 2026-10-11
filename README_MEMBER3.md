# BudgetClear — Member 3 AI Assistance

## Files
- `modules/ai_assist.py` — exact shared function signatures
- `tests/test_ai_assist.py` — focused tests
- `data/category_examples.csv` — fictional labelled examples (50+ rows)
- `docs/INTERFACES_AI_EXCERPT.md` — AI interface notes

## Install and test
From the repository root:
```powershell
python -m pip install scikit-learn pytest
python -m pytest -q tests/test_ai_assist.py
```

## Functions
```python
from modules.ai_assist import suggest_categories, suggest_anomalies

category_suggestions = suggest_categories(transactions)
anomaly_suggestions = suggest_anomalies(transactions)
```

`transactions` is a list of dictionaries with agreed keys such as `transaction_id`, `description`, `category`, and `amount`. The module does not mutate this input.

## Offline-first behavior
The default route uses local TF-IDF + LogisticRegression when scikit-learn and labelled examples are available. If that cannot run, it falls back to deterministic keyword rules. Anomaly suggestions use Decimal arithmetic and the 1.5×IQR rule within categories with at least four usable rows.

Optional local LLM path:
1. Install/start Ollama separately.
2. Run `ollama pull llama3.2`.
3. Set `BUDGETCLEAR_USE_OLLAMA=1` in the environment before starting the app.
4. If Ollama is missing, times out, or returns invalid output, the local fallback is used.

## Safety
- The module never changes verified totals or original transactions.
- It only suggests categories for blank categories.
- Money values are parsed with `Decimal`, not float.
- Findings include evidence transaction IDs and explain the check.
- No alert is a finding of fraud; every alert needs human review.

## Member 3 roadmap
1. Confirm branch `feature/ai-assist` and shared input keys with the team.
2. Add these files without replacing teammates' files.
3. Install dependencies and run the focused tests.
4. Inspect `git status` and stage only your owned files.
5. Commit:
   `git commit -m "add category and anomaly suggestions with fallback"`
6. Sync safely with the latest main using the team's Git workflow.
7. Push:
   `git push -u origin feature/ai-assist`
8. Open a Pull Request into `main`, request review, and coordinate dashboard integration with Member 4.
