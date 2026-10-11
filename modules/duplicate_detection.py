
from difflib import SequenceMatcher


def detect_duplicates(transactions, similarity_threshold=0.80):
    findings = []

    for i, first in enumerate(transactions):
        for second in transactions[i + 1:]:
            date1 = str(first.get("date", "")).strip()
            date2 = str(second.get("date", "")).strip()
            amount1 = str(first.get("amount", "")).strip()
            amount2 = str(second.get("amount", "")).strip()

            if not date1 or not amount1:
                continue

            if date1 != date2 or amount1 != amount2:
                continue

            ref1 = str(first.get("reference", "")).strip().casefold()
            ref2 = str(second.get("reference", "")).strip().casefold()
            desc1 = str(first.get("description", "")).strip().casefold()
            desc2 = str(second.get("description", "")).strip().casefold()

            exact = ref1 == ref2
            score = max(
                SequenceMatcher(None, ref1, ref2).ratio(),
                SequenceMatcher(None, desc1, desc2).ratio(),
            )

            findings.append({
                "title": "Possible duplicate transaction",
                "type": (
                    "exact_duplicate_candidate"
                    if exact else "near_duplicate_candidate"
                ),
                "source": "duplicate_detection",
                "severity": "review",
                "message": (
                    "Matching date, amount and reference."
                    if exact else
                    "Matching date and amount; review reference and description."
                ),
                "evidence_ids": [
                    first.get("transaction_id", "UNKNOWN"),
                    second.get("transaction_id", "UNKNOWN"),
                ],
                "similarity": round(score, 3),
                "review_status": "pending",
                "disclaimer": (
                    "A duplicate candidate is not proof of fraud or wrongdoing."
                ),
            })

    return findings
