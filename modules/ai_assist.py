"""BudgetClear Member 3: AI category and anomaly suggestions.

Public interface (keep compatible with docs/INTERFACES.md):
    suggest_categories(transactions) -> list[dict]
    suggest_anomalies(transactions) -> list[dict]

Safety:
- Input transactions are never mutated.
- Missing categories remain missing until a human accepts a suggestion.
- Money values are parsed with Decimal, never float.
- These are suggestions, not verified findings or accusations.
- Works offline using local examples and deterministic fallback rules.
"""

from __future__ import annotations

import csv
import json
import os
import urllib.request
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "data" / "category_examples.csv"
CONFIDENCE_THRESHOLD = 0.45
OLLAMA_URL = os.getenv("BUDGETCLEAR_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("BUDGETCLEAR_OLLAMA_MODEL", "llama3.2")

ALLOWED_CATEGORIES = {
    "Administration", "Construction", "Equipment", "Food", "Maintenance",
    "Medical", "Office Supplies", "Professional Services", "Training",
    "Travel", "Utilities",
}


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _money(value: Any) -> Decimal | None:
    """Parse a money value exactly; invalid values are skipped, never treated as zero."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = str(value).strip()
    for prefix in ("₹", "Rs.", "Rs", "INR"):
        cleaned = cleaned.replace(prefix, "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _keyword_suggestion(description: str) -> tuple[str | None, float, str]:
    text = description.lower()
    rules = [
        ("Travel", ("taxi", "cab fare", "bus ticket", "train ticket", "flight ticket", "hotel", "travel", "transport", "fuel")),
        ("Office Supplies", ("stationery", "paper", "pens", "pen ", "notebook", "toner", "printer ink", "folders", "registers")),
        ("Utilities", ("electricity", "water bill", "internet bill", "broadband", "telephone bill", "utility charges")),
        ("Equipment", ("laptop", "computer", "projector", "printer equipment", "hardware", "laboratory equipment", "monitor")),
        ("Maintenance", ("repair", "maintenance", "servicing", "plumbing", "painting", "air conditioner")),
        ("Training", ("training", "workshop", "seminar", "course fee", "certification")),
        ("Medical", ("medical", "medicine", "clinic", "first aid", "health check")),
        ("Food", ("catering", "refreshments", "food", "meal", "lunch", "tea and snacks")),
        ("Construction", ("construction", "cement", "steel rods", "building material", "renovation", "bricks")),
        ("Professional Services", ("consultancy", "legal fee", "audit fee", "professional services", "accounting services")),
        ("Administration", ("administrative", "postage", "courier", "public notice", "office administration")),
    ]
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category, 0.55, f"Description keywords match examples commonly labelled {category}."
    return None, 0.0, "Description does not clearly match a known category; manual review is recommended."


def _read_examples() -> tuple[list[str], list[str]]:
    descriptions: list[str] = []
    categories: list[str] = []
    with EXAMPLES_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"description", "category"}.issubset(reader.fieldnames):
            raise ValueError("category_examples.csv must contain description,category columns.")
        for row in reader:
            description = _clean(row.get("description"))
            category = _clean(row.get("category"))
            if description and category in ALLOWED_CATEGORIES:
                descriptions.append(description)
                categories.append(category)
    if len(descriptions) < 6 or len(set(categories)) < 2:
        raise ValueError("Need at least 6 labelled examples from at least 2 categories.")
    return descriptions, categories


@lru_cache(maxsize=1)
def _local_model():
    """Train a small local classifier once; scikit-learn is an optional dependency."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    descriptions, categories = _read_examples()
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(descriptions)
    classifier = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    classifier.fit(matrix, categories)
    return vectorizer, classifier


def _local_category(description: str) -> dict[str, Any]:
    if not description:
        return {
            "suggested_category": None,
            "confidence": 0.0,
            "reason": "Description is empty; manual review is recommended.",
            "source": "fallback_heuristic",
        }
    try:
        vectorizer, classifier = _local_model()
        probabilities = classifier.predict_proba(vectorizer.transform([description]))[0]
        index = max(range(len(probabilities)), key=lambda i: probabilities[i])
        confidence = float(probabilities[index])
        category = str(classifier.classes_[index])
        if confidence < CONFIDENCE_THRESHOLD:
            return {
                "suggested_category": None,
                "confidence": round(confidence, 4),
                "reason": f"Classifier confidence is below {CONFIDENCE_THRESHOLD:.2f}; manual review is recommended.",
                "source": "fallback_heuristic",
            }
        return {
            "suggested_category": category,
            "confidence": round(confidence, 4),
            "reason": f"The description most closely matches labelled examples for {category}.",
            "source": "fallback_heuristic",
        }
    except Exception:
        category, confidence, reason = _keyword_suggestion(description)
        if confidence < CONFIDENCE_THRESHOLD:
            category = None
        return {
            "suggested_category": category,
            "confidence": round(confidence, 4),
            "reason": reason,
            "source": "fallback_heuristic",
        }


def _ollama_category(description: str) -> dict[str, Any] | None:
    """Optional local LLM route. Falls back locally on any error."""
    prompt = (
        "Classify this fictional public-institution expense description. "
        "Return JSON only with keys suggested_category, confidence, reason. "
        "suggested_category must be one of: "
        + ", ".join(sorted(ALLOWED_CATEGORIES))
        + ". If unclear, use null and confidence 0. Do not infer fraud. Description: "
        + json.dumps(description)
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        body = json.loads(response.read().decode("utf-8"))
    parsed = json.loads(body.get("response", "{}"))
    category = parsed.get("suggested_category")
    if category is not None and category not in ALLOWED_CATEGORIES:
        return None
    confidence = float(parsed.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        return None
    if confidence < CONFIDENCE_THRESHOLD:
        category = None
    return {
        "suggested_category": category,
        "confidence": round(confidence, 4),
        "reason": _clean(parsed.get("reason")) or "Local language model suggestion; verify it manually.",
        "source": "ai_model",
    }


def suggest_categories(transactions: Iterable[dict]) -> list[dict]:
    """Suggest a category only when category is blank; do not mutate transactions."""
    suggestions: list[dict] = []
    use_ollama = os.getenv("BUDGETCLEAR_USE_OLLAMA", "").lower() in {"1", "true", "yes"}

    for row in transactions:
        if not isinstance(row, dict) or _clean(row.get("category")):
            continue
        transaction_id = _clean(row.get("transaction_id") or row.get("id"))
        description = _clean(row.get("description"))

        result = None
        if use_ollama and description:
            try:
                result = _ollama_category(description)
            except Exception:
                result = None

        if result is None:
            result = _local_category(description)

        suggestions.append({
            "transaction_id": transaction_id,
            "suggested_category": result["suggested_category"],
            "confidence": result["confidence"],
            "reason": result["reason"],
            "source": result["source"],
            "review_status": "needs_review",
        })
    return suggestions


def _quantile(values: list[Decimal], fraction: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def suggest_anomalies(transactions: Iterable[dict]) -> list[dict]:
    """Suggest amount outliers within a category using 1.5*IQR.

    A finding is a review candidate only. Amounts are parsed using Decimal and the
    input rows are never changed.
    """
    groups: dict[str, list[tuple[str, Decimal]]] = {}
    for row in transactions:
        if not isinstance(row, dict):
            continue
        category = _clean(row.get("category"))
        transaction_id = _clean(row.get("transaction_id") or row.get("id"))
        amount = _money(row.get("amount"))
        if not category or not transaction_id or amount is None:
            continue
        groups.setdefault(category, []).append((transaction_id, amount))

    findings: list[dict] = []
    for category, members in groups.items():
        if len(members) < 4:
            continue
        amounts = [amount for _, amount in members]
        q1 = _quantile(amounts, Decimal("0.25"))
        q3 = _quantile(amounts, Decimal("0.75"))
        iqr = q3 - q1
        lower = q1 - Decimal("1.5") * iqr
        upper = q3 + Decimal("1.5") * iqr
        comparison_ids = [transaction_id for transaction_id, _ in members]

        for transaction_id, amount in members:
            if amount < lower or amount > upper:
                direction = "higher" if amount > upper else "lower"
                findings.append({
                    "transaction_id": transaction_id,
                    "severity": "medium",
                    "message": f"Amount is unusually {direction} than other entries in category '{category}'.",
                    "reason": (
                        f"Amount {amount} is outside the IQR review range [{lower}, {upper}] "
                        f"for {len(members)} records in category '{category}'. "
                        "This is a review suggestion, not proof of wrongdoing."
                    ),
                    "source": "fallback_heuristic",
                    "evidence_transaction_ids": comparison_ids,
                    "check_performed": "1.5x interquartile range (IQR) within category",
                    "review_status": "needs_review",
                })
    return findings
