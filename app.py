

import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from modules.validation import validate_transactions
from modules.reconciliation import reconcile_budget
from modules.duplicate_detection import detect_duplicates
from modules.ai_assist import suggest_categories, suggest_anomalies


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="BudgetClear",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DISCLAIMER = (
    "An anomaly flag is not proof of corruption or wrongdoing. "
    "Every flag requires human investigation."
)

SAMPLE_TRANSACTIONS = [
    {
        "transaction_id": "TXN-001",
        "date": "2026-09-01",
        "description": "Office stationery",
        "category": "Office Supplies",
        "amount": "2500.00",
        "reference": "REF-101",
    },
    {
        "transaction_id": "TXN-002",
        "date": "2026-09-02",
        "description": "Computer equipment",
        "category": "IT Equipment",
        "amount": "18500.00",
        "reference": "REF-102",
    },
    {
        "transaction_id": "TXN-003",
        "date": "2026-09-03",
        "description": "Office cleaning",
        "category": "Maintenance",
        "amount": "4000.00",
        "reference": "REF-103",
    },
    {
        "transaction_id": "TXN-004",
        "date": "2026-09-04",
        "description": "Office stationery supplies",
        "category": "",
        "amount": "1500.00",
        "reference": "REF-104",
    },
    {
        "transaction_id": "TXN-005",
        "date": "2026-09-05",
        "description": "IT accessories",
        "category": "IT Equipment",
        "amount": "3000.00",
        "reference": "REF-105",
    },
]

DEFAULT_CATEGORY_TOTALS = {
    "Office Supplies": "2500.00",
    "IT Equipment": "21500.00",
    "Maintenance": "4000.00",
}


# --------------------------------------------------
# STYLING
# --------------------------------------------------

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        max-width: 1450px;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(120,130,150,.2);
    }

    .hero {
        padding: 1.5rem;
        border-radius: 16px;
        color: white;
        background: linear-gradient(
            120deg, #14253d, #203e5e, #23645e
        );
        margin-bottom: 1rem;
    }

    .hero h1 {
        color: white;
        margin: 0 0 .4rem 0;
    }

    .hero p {
        color: #e0eaf3;
        margin: 0;
    }

    div[data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(120,130,150,.2);
        padding: 1rem;
        border-radius: 12px;
    }

    div.stButton > button,
    div.stDownloadButton > button {
        border-radius: 9px;
        min-height: 2.5rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

def initialise_state():
    defaults = {
        "transactions": None,
        "input_source": None,
        "review_decisions": {},
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def load_sample():
    st.session_state.transactions = pd.DataFrame(
        deepcopy(SAMPLE_TRANSACTIONS)
    )
    st.session_state.input_source = "Fictional demo data"
    st.session_state.review_decisions = {}


# --------------------------------------------------
# CSV LOADING
# --------------------------------------------------

def prepare_uploaded_csv(uploaded_file):
    """Load standard transaction CSV files."""

    frame = pd.read_csv(
        uploaded_file,
        dtype=str,
        keep_default_na=False,
    )

    frame.columns = [
        str(column)
        .strip()
        .lstrip("\ufeff")
        .lower()
        .replace(" ", "_")
        for column in frame.columns
    ]

    frame = frame.drop(
        columns=[
            column
            for column in frame.columns
            if column.startswith("unnamed:")
        ],
        errors="ignore",
    )

    if frame.empty:
        raise ValueError("The CSV contains no data rows.")

    required = [
        "date",
        "description",
        "category",
        "amount",
        "reference",
    ]

    missing = [
        column for column in required
        if column not in frame.columns
    ]

    if missing:
        raise ValueError(
            "Missing required transaction columns: "
            + ", ".join(missing)
            + ". This upload handler expects a standard transaction CSV."
        )

    if "transaction_id" not in frame.columns:
        frame.insert(
            0,
            "transaction_id",
            [
                f"TXN-{i:06d}"
                for i in range(1, len(frame) + 1)
            ],
        )

    frame["amount_unit"] = "INR"
    frame["dataset_type"] = "transactions"

    return frame


# --------------------------------------------------
# DISPLAY FINDINGS
# --------------------------------------------------

def display_findings(records, empty_message):
    if records is None or len(records) == 0:
        st.info(empty_message)
        return

    for index, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            st.write(item)
            continue

        title = (
            item.get("title")
            or item.get("transaction_id")
            or item.get("finding_type")
            or f"Finding {index}"
        )

        message = (
            item.get("message")
            or item.get("reason")
            or item.get("description")
            or ""
        )

        severity = str(
            item.get("severity", "Review")
        ).replace("_", " ").title()

        with st.container(border=True):
            left, right = st.columns([5, 1])

            with left:
                st.markdown(f"**{title}**")

                if message:
                    st.write(message)

                if item.get("transaction_id"):
                    st.caption(
                        f"Transaction: {item['transaction_id']}"
                    )

                evidence = (
                    item.get("evidence_transaction_ids")
                    or item.get("evidence_ids")
                )

                if evidence:
                    st.caption(
                        "Related transactions: "
                        + ", ".join(str(value) for value in evidence)
                    )

            with right:
                st.caption("Severity")
                st.markdown(f"**{severity}**")


# --------------------------------------------------
# MAIN APPLICATION
# --------------------------------------------------

def main():
    initialise_state()

    # Sidebar
    with st.sidebar:
        st.markdown("## 📊 BudgetClear")
        st.caption("Public Spending Reconciliation")
        st.divider()

        st.markdown("**VORTEXA 3.0**")
        st.caption("Problem Statement G-03")
        st.divider()

        st.markdown("### Workflow")
        st.caption("01 · Load records")
        st.caption("02 · Validate data")
        st.caption("03 · Reconcile totals")
        st.caption("04 · Detect duplicates")
        st.caption("05 · Human review")
        st.caption("06 · Export report")

        st.divider()
        st.caption(
            "Fictional data recommended for demonstrations."
        )

    # Hero
    st.markdown(
        """
        <div class="hero">
            <h1>BudgetClear</h1>
            <p>Public Spending Reconciliation &amp; Anomaly Review</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.warning(DISCLAIMER)

    # --------------------------------------------------
    # 1. LOAD RECORDS
    # --------------------------------------------------

    st.header("1. Load spending records")

    upload_col, demo_col = st.columns(2)

    with upload_col:
        uploaded_file = st.file_uploader(
            "Upload transaction CSV",
            type=["csv"],
            help=(
                "Required columns: date, description, "
                "category, amount and reference."
            ),
        )

        if st.button(
            "Load uploaded CSV",
            type="primary",
            use_container_width=True,
        ):
            if uploaded_file is None:
                st.warning("Choose a CSV file first.")
            else:
                try:
                    uploaded_file.seek(0)

                    loaded_frame = prepare_uploaded_csv(
                        uploaded_file
                    )

                    st.session_state.transactions = loaded_frame
                    st.session_state.input_source = uploaded_file.name
                    st.session_state.review_decisions = {}

                    st.success("CSV loaded successfully.")
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not load CSV: {error}")

    with demo_col:
        st.write("Use fictional records to try the dashboard.")

        st.button(
            "Load demo data",
            on_click=load_sample,
            use_container_width=True,
        )

    transactions = st.session_state.transactions

    if transactions is None:
        st.info(
            "Upload a transaction CSV or click Load demo data to begin."
        )
        st.stop()

    # Preserve original records
    original_df = transactions.copy(deep=True)

    original_records = (
        original_df.fillna("")
        .astype(str)
        .to_dict("records")
    )

    # --------------------------------------------------
    # 2. VALIDATION
    # --------------------------------------------------

    try:
        validation = validate_transactions(original_records)

        normalized_records = validation.get(
            "normalized_transactions",
            original_records,
        )

        validation_errors = validation.get("errors", [])
        validation_warnings = validation.get("warnings", [])
        validation_error = None

    except Exception as error:
        normalized_records = original_records
        validation_errors = [{"message": str(error)}]
        validation_warnings = []
        validation_error = str(error)

    missing_categories = int(
        original_df["category"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    missing_amounts = int(
        original_df["amount"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    # --------------------------------------------------
    # 3. DASHBOARD OVERVIEW
    # --------------------------------------------------

    st.divider()
    st.header("2. Dashboard overview")
    st.caption(f"Source: {st.session_state.input_source}")

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Transactions", len(original_df))
    m2.metric("Missing categories", missing_categories)
    m3.metric("Missing amounts", missing_amounts)
    m4.metric("Validation issues", len(validation_errors))

    with st.expander("Preview original transactions"):
        st.dataframe(
            original_df,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------
    # 4. DECLARED BUDGET TOTALS
    # JSON TEXT INPUT REMOVED
    # --------------------------------------------------

    st.divider()
    st.header("3. Declared budget totals")

    st.caption(
        "Enter the amounts stated in the budget document. "
        "These example values are not authoritative figures."
    )

    total_col, category_col = st.columns(2)

    with total_col:
        stated_grand_total = st.text_input(
            "Stated grand total (₹)",
            value="29500.00",
            key="stated_grand_total_input",
        )

    with category_col:
        st.markdown("#### Declared category totals")

        stated_category_totals = {}

        for category, default_amount in DEFAULT_CATEGORY_TOTALS.items():
            stated_category_totals[category] = st.text_input(
                f"{category} (₹)",
                value=default_amount,
                key=f"category_total_{category}",
            )

        with st.expander("Add another category"):
            extra_category = st.text_input(
                "Category name",
                key="extra_category_name",
            )

            extra_amount = st.text_input(
                "Declared amount (₹)",
                value="0.00",
                key="extra_category_amount",
            )

            if extra_category.strip():
                stated_category_totals[
                    extra_category.strip()
                ] = extra_amount

    # Validate numeric amounts without parsing JSON.
    budget_input_error = None

    try:
        Decimal(stated_grand_total.strip())

        for category, amount in stated_category_totals.items():
            Decimal(str(amount).strip())

    except (InvalidOperation, ValueError, AttributeError):
        budget_input_error = (
            "Enter a valid numeric amount in every budget field."
        )

    if budget_input_error:
        st.error(budget_input_error)

    # --------------------------------------------------
    # 5. RECONCILIATION
    # --------------------------------------------------

    try:
        if budget_input_error:
            raise ValueError(budget_input_error)

        verified_findings = reconcile_budget(
            normalized_records,
            Decimal(stated_grand_total.strip()),
            {
                category: Decimal(str(amount).strip())
                for category, amount in stated_category_totals.items()
            },
        )

        reconciliation_error = None

    except Exception as error:
        verified_findings = []
        reconciliation_error = str(error)

    # --------------------------------------------------
    # 6. DUPLICATE DETECTION
    # --------------------------------------------------

    try:
        duplicate_findings = detect_duplicates(normalized_records)
        duplicate_error = None

    except Exception as error:
        duplicate_findings = []
        duplicate_error = str(error)

    # --------------------------------------------------
    # 7. AI ASSISTANCE
    # --------------------------------------------------

    try:
        category_suggestions = suggest_categories(normalized_records)
        category_error = None

    except Exception as error:
        category_suggestions = []
        category_error = str(error)

    try:
        ai_anomalies = suggest_anomalies(normalized_records)
        anomaly_error = None

    except Exception as error:
        ai_anomalies = []
        anomaly_error = str(error)

    # --------------------------------------------------
    # 8. FINDINGS AND REVIEW
    # --------------------------------------------------

    st.divider()
    st.header("4. Findings and review")

    verified_tab, quality_tab, ai_tab, review_tab = st.tabs(
        [
            "Verified findings",
            "Data quality & duplicates",
            "AI suggestions",
            "Human review",
        ]
    )

    with verified_tab:
        st.subheader("Rule-based reconciliation")

        if reconciliation_error:
            st.error(
                f"Reconciliation failed: {reconciliation_error}"
            )
        else:
            display_findings(
                verified_findings,
                "No reconciliation findings returned.",
            )

        st.caption(
            "A discrepancy is a reason to investigate, "
            "not proof of wrongdoing."
        )

    with quality_tab:
        st.subheader("Validation")

        if validation_error:
            st.error(f"Validation failed: {validation_error}")

        display_findings(
            validation_errors,
            "No validation errors reported.",
        )

        if validation_warnings:
            st.markdown("**Warnings**")
            display_findings(
                validation_warnings,
                "No validation warnings.",
            )

        st.divider()
        st.subheader("Potential duplicates")

        if duplicate_error:
            st.error(
                f"Duplicate detection failed: {duplicate_error}"
            )
        else:
            display_findings(
                duplicate_findings,
                "No duplicate candidates returned.",
            )

        st.divider()
        st.subheader("Missing categories")

        missing_rows = original_df[
            original_df["category"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
        ]

        if missing_rows.empty:
            st.success("No missing categories.")
        else:
            st.warning(
                f"{len(missing_rows)} record(s) have a missing category."
            )
            st.dataframe(
                missing_rows,
                use_container_width=True,
                hide_index=True,
            )

    with ai_tab:
        st.subheader("Category suggestions")

        if category_error:
            st.error(
                f"Category suggestions failed: {category_error}"
            )
        else:
            display_findings(
                category_suggestions,
                "No category suggestions returned.",
            )

        st.divider()
        st.subheader("Potential anomalies")

        if anomaly_error:
            st.error(
                f"Anomaly analysis failed: {anomaly_error}"
            )
        else:
            display_findings(
                ai_anomalies,
                "No potential anomalies returned.",
            )

    # --------------------------------------------------
    # 9. HUMAN REVIEW
    # --------------------------------------------------

    with review_tab:
        st.subheader("Review queue")

        if category_error:
            st.error(
                "Resolve the category suggestion error before reviewing."
            )

        elif not category_suggestions:
            st.info("No category suggestions to review.")

        else:
            for index, suggestion in enumerate(category_suggestions):
                if not isinstance(suggestion, dict):
                    continue

                transaction_id = str(
                    suggestion.get("transaction_id", "")
                )

                proposed = str(
                    suggestion.get("suggested_category") or ""
                ).strip()

                decision_key = f"category:{transaction_id}"

                status = st.session_state.review_decisions.get(
                    decision_key,
                    "pending",
                )

                description = next(
                    (
                        row.get("description", "")
                        for row in normalized_records
                        if str(row.get("transaction_id", ""))
                        == transaction_id
                    ),
                    "",
                )

                with st.container(border=True):
                    st.markdown(f"**Transaction {transaction_id}**")
                    st.write(f"Description: {description}")
                    st.write(
                        f"Suggested category: "
                        f"**{proposed or 'No reliable suggestion'}**"
                    )
                    st.caption(f"Review status: {status.title()}")

                    accept_col, reject_col = st.columns(2)

                    with accept_col:
                        if st.button(
                            "Accept suggestion",
                            key=f"accept_{index}_{transaction_id}",
                            disabled=(
                                not proposed or status == "accepted"
                            ),
                            use_container_width=True,
                        ):
                            st.session_state.review_decisions[
                                decision_key
                            ] = "accepted"
                            st.rerun()

                    with reject_col:
                        if st.button(
                            "Reject suggestion",
                            key=f"reject_{index}_{transaction_id}",
                            disabled=status == "rejected",
                            use_container_width=True,
                        ):
                            st.session_state.review_decisions[
                                decision_key
                            ] = "rejected"
                            st.rerun()

        if st.session_state.review_decisions:
            st.markdown("**Recorded decisions**")
            st.json(st.session_state.review_decisions)
        else:
            st.caption("No review decisions recorded.")

    # --------------------------------------------------
    # 10. REVIEWED WORKING COPY
    # --------------------------------------------------

    reviewed_records = deepcopy(normalized_records)

    suggestion_by_id = {
        str(item.get("transaction_id", "")): item
        for item in category_suggestions
        if isinstance(item, dict)
    }

    for transaction_id, suggestion in suggestion_by_id.items():
        proposed = str(
            suggestion.get("suggested_category") or ""
        ).strip()

        decision_key = f"category:{transaction_id}"

        if (
            proposed
            and st.session_state.review_decisions.get(decision_key)
            == "accepted"
        ):
            for row in reviewed_records:
                if (
                    str(row.get("transaction_id", ""))
                    == transaction_id
                    and not str(row.get("category", "")).strip()
                ):
                    row["category"] = proposed

    # --------------------------------------------------
    # 11. EXPORT REPORT
    # --------------------------------------------------

    st.divider()
    st.header("5. Export report")

    module_errors = {
        "validation": validation_error,
        "reconciliation": reconciliation_error,
        "duplicates": duplicate_error,
        "category_suggestions": category_error,
        "anomaly_analysis": anomaly_error,
    }

    report = {
        "project": "BudgetClear",
        "problem_statement": "VORTEXA 3.0 G-03",
        "input_source": st.session_state.input_source,
        "transaction_count": len(original_df),
        "stated_grand_total": stated_grand_total,
        "stated_category_totals": stated_category_totals,
        "verified_findings": verified_findings,
        "data_quality_findings": {
            "errors": validation_errors,
            "warnings": validation_warnings,
        },
        "duplicate_findings": duplicate_findings,
        "ai_suggestions": {
            "category_suggestions": category_suggestions,
            "potential_anomalies": ai_anomalies,
        },
        "review_decisions": st.session_state.review_decisions,
        "original_transactions": original_records,
        "reviewed_transactions": reviewed_records,
        "module_errors": module_errors,
        "disclaimer": DISCLAIMER,
        "status": (
            "Analysis completed with module errors; inspect module_errors."
            if any(module_errors.values())
            else "Analysis completed; human review may still be required."
        ),
    }

    csv_col, reviewed_col, json_col = st.columns(3)

    with csv_col:
        st.download_button(
            "Download original CSV",
            data=original_df.to_csv(index=False).encode("utf-8"),
            file_name="budgetclear_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with reviewed_col:
        st.download_button(
            "Download reviewed CSV",
            data=pd.DataFrame(reviewed_records)
            .to_csv(index=False)
            .encode("utf-8"),
            file_name="budgetclear_reviewed_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with json_col:
        st.download_button(
            "Download analysis JSON",
            data=json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8"),
            file_name="budgetclear_report.json",
            mime="application/json",
            use_container_width=True,
        )

    st.caption(
        "Original records remain unchanged. Accepted suggestions affect "
        "only the reviewed copy. All flags require human investigation."
    )

    st.divider()
    st.caption(
        "BudgetClear · VORTEXA 3.0 · Fictional data for demonstration"
    )


if __name__ == "__main__":
    main()
