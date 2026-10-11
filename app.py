
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.validation import validate_transactions
from modules.reconciliation import reconcile_budget
from modules.duplicate_detection import detect_duplicates
from modules.ai_assist import suggest_categories, suggest_anomalies


st.set_page_config(
    page_title="BudgetClear",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load the external dashboard theme.
st.markdown(
    "<style>\n"
    + Path("assets/dashboard.css").read_text(encoding="utf-8")
    + "\n</style>",
    unsafe_allow_html=True,
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
# Styling
# --------------------------------------------------

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1450px;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(120, 130, 150, 0.2);
    }

    .hero {
        padding: 1.7rem;
        border-radius: 16px;
        color: white;
        background: linear-gradient(
            120deg, #14253d, #203e5e, #23645e
        );
        margin-bottom: 1rem;
    }

    .hero h1 {
        color: white;
        margin: 0 0 0.4rem 0;
        font-size: 2.2rem;
    }

    .hero p {
        color: #e0eaf3;
        margin: 0;
        font-size: 1rem;
    }

    div[data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(120, 130, 150, 0.2);
        padding: 1rem;
        border-radius: 12px;
    }

    div.stButton > button,
    div.stDownloadButton > button {
        border-radius: 9px;
        min-height: 2.5rem;
        font-weight: 600;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# State and data helpers
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


def prepare_uploaded_csv(uploaded_file):
    frame = pd.read_csv(
        uploaded_file,
        dtype=str,
        keep_default_na=False,
    )

    frame.columns = [
        str(column).strip().lower().replace(" ", "_")
        for column in frame.columns
    ]

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
            "Missing required CSV columns: "
            + ", ".join(missing)
        )

    if frame.empty:
        raise ValueError("The CSV contains no transaction rows.")

    if "transaction_id" not in frame.columns:
        frame.insert(
            0,
            "transaction_id",
            [f"TXN-{i:03d}" for i in range(1, len(frame) + 1)],
        )

    return frame


def safe_amount(value):
    """Return a Decimal for valid amounts, otherwise None."""
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        amount = Decimal(text)
        if not amount.is_finite():
            return None
        return amount
    except (InvalidOperation, ValueError):
        return None


def format_inr(amount):
    """Format an amount as INR without using float arithmetic."""
    return f"₹{amount:,.2f}"


def calculate_amount_total(records):
    """Sum parseable amounts. Invalid values are excluded."""
    total = Decimal("0.00")
    valid_count = 0
    invalid_count = 0

    for row in records:
        amount = safe_amount(row.get("amount"))

        if amount is None:
            invalid_count += 1
            continue

        total += amount
        valid_count += 1

    return total, valid_count, invalid_count


def display_findings(records, empty_message):
    """Render findings as readable cards."""
    if not records:
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
            item.get("severity", "review")
        ).replace("_", " ").title()

        source = item.get("source", "Analysis module")

        evidence = (
            item.get("evidence_transaction_ids")
            or item.get("evidence_ids")
        )

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

                if evidence:
                    st.caption(
                        "Related transactions: "
                        + ", ".join(str(value) for value in evidence)
                    )

                difference = item.get("amount_difference")
                if difference is not None:
                    parsed_difference = safe_amount(difference)
                    if parsed_difference is not None:
                        st.caption(
                            "Amount difference: "
                            + format_inr(parsed_difference)
                        )

            with right:
                st.caption("Severity")
                st.markdown(f"**{severity}**")

            st.caption(f"Source: {source}")


def show_module_error(label, error):
    if error:
        st.error(f"{label}: {error}")


# --------------------------------------------------
# Main dashboard
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
        st.caption("Fictional data recommended for demonstrations.")

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

    # ----------------------------------------------
    # 1. Load data
    # ----------------------------------------------

    st.header("1. Load spending records")

    upload_col, demo_col = st.columns(2)

    with upload_col:
        uploaded_file = st.file_uploader(
            "Upload transaction CSV",
            type=["csv"],
            help=(
                "Required columns: date, description, category, "
                "amount and reference. Transaction ID is optional."
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
                    loaded_frame = prepare_uploaded_csv(uploaded_file)

                    st.session_state.transactions = loaded_frame
                    st.session_state.input_source = uploaded_file.name
                    st.session_state.review_decisions = {}

                    st.success("CSV loaded successfully.")
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not load CSV: {error}")

    with demo_col:
        st.write("Try the application using fictional transaction records.")
        st.button(
            "Load demo data",
            on_click=load_sample,
            use_container_width=True,
        )

    transactions = st.session_state.transactions

    if transactions is None:
        st.info("Upload a CSV or load demo data to begin.")
        st.stop()

    original_df = transactions.copy(deep=True)

    original_records = (
        original_df.fillna("")
        .astype(str)
        .to_dict("records")
    )

    # ----------------------------------------------
    # 2. Validation
    # ----------------------------------------------

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

    recorded_total, valid_amount_count, invalid_amount_count = (
        calculate_amount_total(normalized_records)
    )

    # ----------------------------------------------
    # 3. Dashboard overview
    # ----------------------------------------------

    st.divider()
    st.header("2. Dashboard overview")
    st.caption(f"Input source: {st.session_state.input_source}")

    metric1, metric2, metric3 = st.columns(3)

    metric1.metric("Total transactions", f"{len(original_df):,}")
    metric2.metric(
        "Recorded amount total",
        format_inr(recorded_total),
        help="Sum of parseable transaction amounts. Invalid amounts are excluded.",
    )
    metric3.metric("Validation errors", f"{len(validation_errors):,}")

    metric4, metric5, metric6 = st.columns(3)

    metric4.metric("Missing categories", f"{missing_categories:,}")
    metric5.metric("Missing amounts", f"{missing_amounts:,}")
    metric6.metric("Validation warnings", f"{len(validation_warnings):,}")

    if invalid_amount_count:
        st.warning(
            f"{invalid_amount_count} transaction amount(s) could not "
            "be parsed and were excluded from the recorded amount total."
        )

    st.caption(
        f"Amounts counted in the total: {valid_amount_count} "
        f"of {len(normalized_records)} transaction(s)."
    )

    # ----------------------------------------------
    # Spending analytics
    # ----------------------------------------------

    st.subheader("Spending analytics")
    st.caption(
        "Explore recorded spending by category and date. "
        "Transactions with invalid amounts are excluded."
    )

    category_totals_for_chart = {}
    daily_totals_for_chart = {}

    for record in normalized_records:
        amount = safe_amount(record.get("amount"))
        if amount is None:
            continue

        category = str(record.get("category") or "").strip()
        if not category:
            category = "Uncategorized"

        category_totals_for_chart[category] = (
            category_totals_for_chart.get(category, Decimal("0.00"))
            + amount
        )

        date_text = str(record.get("date") or "").strip()
        if date_text:
            parsed_date = pd.to_datetime(date_text, errors="coerce")
            if not pd.isna(parsed_date):
                date_key = parsed_date.strftime("%Y-%m-%d")
                daily_totals_for_chart[date_key] = (
                    daily_totals_for_chart.get(date_key, Decimal("0.00"))
                    + amount
                )

    chart_col1, chart_col2 = st.columns(2, gap="large")

    with chart_col1:
        with st.container(border=True):
            st.markdown("#### Spending by category")
            st.caption("Recorded amount · INR")

            if category_totals_for_chart:
                category_chart = pd.DataFrame([
                    {
                        "Category": category,
                        "Amount (₹)": float(amount),
                    }
                    for category, amount in sorted(
                        category_totals_for_chart.items(),
                        key=lambda item: item[1],
                    )
                ])

                st.bar_chart(
                    category_chart,
                    x="Amount (₹)",
                    y="Category",
                    horizontal=True,
                    height=max(260, 58 * len(category_chart)),
                    width="stretch",
                    x_label="Amount (₹)",
                    y_label="",
                )

                st.caption(
                    f"{len(category_chart)} categories · "
                    f"{format_inr(sum(category_totals_for_chart.values(), Decimal('0.00')))} total"
                )
            else:
                st.info("No valid amounts are available for this chart.")

    with chart_col2:
        with st.container(border=True):
            st.markdown("#### Spending over time")
            st.caption("Daily recorded amount · INR")

            if daily_totals_for_chart:
                daily_chart = pd.DataFrame([
                    {
                        "Date": pd.to_datetime(date),
                        "Amount (₹)": float(amount),
                    }
                    for date, amount in sorted(daily_totals_for_chart.items())
                ])

                st.line_chart(
                    daily_chart,
                    x="Date",
                    y="Amount (₹)",
                    height=340,
                    width="stretch",
                    x_label="Transaction date",
                    y_label="Amount (₹)",
                )

                st.caption(
                    f"{len(daily_chart)} dates · "
                    f"{format_inr(sum(daily_totals_for_chart.values(), Decimal('0.00')))} total"
                )
            else:
                st.info("No valid dated amounts are available for the trend chart.")

    st.caption(
        "Charts are summaries, not proof of wrongdoing, and do not replace "
        "the verified reconciliation findings."
    )

    with st.expander("Preview original transactions"):
        st.dataframe(
            original_df,
            use_container_width=True,
            hide_index=True,
        )

    # ----------------------------------------------
    # 4. Declared budget totals — separate fields
    # ----------------------------------------------

    st.divider()
    st.header("3. Declared budget totals")

    st.caption(
        "Enter the totals stated in the budget document. "
        "The demo defaults are examples, not authoritative figures."
    )

    total_col, categories_col = st.columns([1, 1.5], gap="large")

    with total_col:
        stated_grand_total = st.text_input(
            "Stated grand total (₹)",
            value="29500.00",
            key="grand_total",
            help="Enter the grand total declared in the source budget.",
        )

    with categories_col:
        st.markdown("#### Declared category totals")
        st.caption(
            "Enter each amount from the budget document. "
            "You do not need to edit JSON."
        )

        stated_category_totals = {}
        category_columns = st.columns(2, gap="medium")

        for index, (category, default_amount) in enumerate(
            DEFAULT_CATEGORY_TOTALS.items()
        ):
            with category_columns[index % 2]:
                stated_category_totals[category] = st.text_input(
                    f"{category} (₹)",
                    value=default_amount,
                    key=f"budget_category_{category}",
                    help=f"Declared budget amount for {category}.",
                )

        with st.expander("Add another budget category"):
            extra_category_name = st.text_input(
                "Category name",
                key="extra_budget_category_name",
                placeholder="e.g. Transport",
            )
            extra_category_amount = st.text_input(
                "Category amount (₹)",
                value="0.00",
                key="extra_budget_category_amount",
                help="Enter the declared amount for this additional category.",
            )

            if extra_category_name.strip():
                if extra_category_name.strip() in stated_category_totals:
                    st.warning(
                        "That category already exists. "
                        "Edit its existing amount instead."
                    )
                else:
                    stated_category_totals[extra_category_name.strip()] = (
                        extra_category_amount
                    )

    # JSON is used for the downloadable report, not as a user input.
    json_error = None

    # ----------------------------------------------
    # 5. Run analysis modules
    # ----------------------------------------------

    try:
        verified_findings = reconcile_budget(
            normalized_records,
            stated_grand_total,
            stated_category_totals,
        )
        reconciliation_error = None

    except Exception as error:
        verified_findings = []
        reconciliation_error = str(error)

    try:
        duplicate_findings = detect_duplicates(normalized_records)
        duplicate_error = None

    except Exception as error:
        duplicate_findings = []
        duplicate_error = str(error)

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

    # Clear accepted decisions if the suggestion is no longer usable.
    suggestion_by_id = {
        str(item.get("transaction_id", "")): item
        for item in category_suggestions
        if isinstance(item, dict)
    }

    for transaction_id, suggestion in suggestion_by_id.items():
        decision_key = f"category:{transaction_id}"

        proposed = str(
            suggestion.get("suggested_category") or ""
        ).strip()

        if (
            st.session_state.review_decisions.get(decision_key) == "accepted"
            and not proposed
        ):
            st.session_state.review_decisions.pop(decision_key, None)

    # ----------------------------------------------
    # 6. Findings and review
    # ----------------------------------------------

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

        show_module_error("Reconciliation failed", reconciliation_error)

        if not reconciliation_error:
            if verified_findings:
                st.warning(
                    f"{len(verified_findings)} finding(s) need inspection."
                )
                display_findings(
                    verified_findings,
                    "No reconciliation findings returned.",
                )
            else:
                st.success("No reconciliation findings returned.")

        st.caption(
            "A discrepancy is a reason to investigate, "
            "not proof of wrongdoing."
        )

    with quality_tab:
        st.subheader("Validation")

        show_module_error("Validation failed", validation_error)

        if validation_errors:
            display_findings(
                validation_errors,
                "No validation errors.",
            )
        elif not validation_error:
            st.success("No validation errors reported.")

        if validation_warnings:
            st.markdown("**Warnings**")
            display_findings(
                validation_warnings,
                "No warnings.",
            )

        st.divider()
        st.subheader("Potential duplicates")

        show_module_error("Duplicate detection failed", duplicate_error)

        if not duplicate_error:
            if duplicate_findings:
                display_findings(
                    duplicate_findings,
                    "No duplicate candidates returned.",
                )
            else:
                st.info("No duplicate candidates returned.")

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

        show_module_error("Category suggestions failed", category_error)

        if not category_error:
            display_findings(
                category_suggestions,
                "No category suggestions returned.",
            )

        st.divider()
        st.subheader("Potential anomalies")

        show_module_error("Anomaly analysis failed", anomaly_error)

        if not anomaly_error:
            display_findings(
                ai_anomalies,
                "No potential anomalies returned.",
            )

        st.caption(
            "AI-generated suggestions are advisory and require human review."
        )

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
                        "Suggested category: "
                        f"**{proposed or 'No reliable suggestion'}**"
                    )

                    confidence = suggestion.get("confidence")
                    if confidence is not None:
                        try:
                            st.caption(
                                f"Suggestion confidence: {float(confidence):.0%}"
                            )
                        except (TypeError, ValueError):
                            pass

                    reason = suggestion.get("reason")
                    if reason:
                        st.caption(str(reason))

                    st.caption(f"Review status: {status.title()}")

                    accept_col, reject_col = st.columns(2)

                    with accept_col:
                        if st.button(
                            "Accept suggestion",
                            key=f"accept_{index}_{transaction_id}",
                            disabled=not proposed or status == "accepted",
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
            st.markdown("**Recorded review decisions**")

            decision_rows = [
                {
                    "Transaction": key.removeprefix("category:"),
                    "Decision": value.title(),
                }
                for key, value in st.session_state.review_decisions.items()
            ]

            st.dataframe(
                pd.DataFrame(decision_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No review decisions recorded.")

    # ----------------------------------------------
    # 7. Prepare reviewed copy
    # ----------------------------------------------

    reviewed_records = deepcopy(normalized_records)

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
                    str(row.get("transaction_id", "")) == transaction_id
                    and not str(row.get("category", "")).strip()
                ):
                    row["category"] = proposed

    # ----------------------------------------------
    # 8. Export report
    # ----------------------------------------------

    st.divider()
    st.header("5. Export report")

    st.write(
        "Download the original data, the reviewed working copy, "
        "or the complete analysis report."
    )

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
        "recorded_amount_total": str(recorded_total),
        "valid_amount_count": valid_amount_count,
        "invalid_amount_count": invalid_amount_count,
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

    original_csv = original_df.to_csv(index=False).encode("utf-8")

    reviewed_df = pd.DataFrame(reviewed_records)
    reviewed_csv = reviewed_df.to_csv(index=False).encode("utf-8")

    report_json = json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    export1, export2, export3 = st.columns(3)

    with export1:
        st.download_button(
            "Download original CSV",
            data=original_csv,
            file_name="budgetclear_original_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with export2:
        st.download_button(
            "Download reviewed CSV",
            data=reviewed_csv,
            file_name="budgetclear_reviewed_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with export3:
        st.download_button(
            "Download analysis JSON",
            data=report_json,
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
