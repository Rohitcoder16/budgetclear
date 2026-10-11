from modules.reconciliation import reconcile_budget
from modules.ai_assist import suggest_categories, suggest_anomalies
import json as json_lib

import pandas as pd
import streamlit as st




# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="BudgetClear",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------
# 2. CONSTANTS AND FICTIONAL SAMPLE DATA
# --------------------------------------------------

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
        "description": "Department supplies",
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


# --------------------------------------------------
# 3. SESSION STATE
# --------------------------------------------------

def initialise_state():
    if "transactions" not in st.session_state:
        st.session_state.transactions = None

    if "input_source" not in st.session_state:
        st.session_state.input_source = None

    if "review_decisions" not in st.session_state:
        st.session_state.review_decisions = {}


def load_sample():
    st.session_state.transactions = pd.DataFrame(
        SAMPLE_TRANSACTIONS
    )
    st.session_state.input_source = "Fictional demo data"
    st.session_state.review_decisions = {}


# --------------------------------------------------
# 4. CSV LOADER
# --------------------------------------------------

def prepare_uploaded_csv(uploaded_file):
    """Load CSV data without silently dropping rows."""

    frame = pd.read_csv(
        uploaded_file,
        dtype=str,
        keep_default_na=False,
    )

    # Standardise column names.
    frame.columns = [
        str(column).strip().lower().replace(" ", "_")
        for column in frame.columns
    ]

    required_columns = [
        "date",
        "description",
        "category",
        "amount",
        "reference",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in frame.columns
    ]

    if missing_columns:
        raise ValueError(
            "Your CSV is missing these required columns: "
            + ", ".join(missing_columns)
        )

    if "transaction_id" not in frame.columns:
        frame.insert(
            0,
            "transaction_id",
            [
                f"TXN-{number:03d}"
                for number in range(1, len(frame) + 1)
            ],
        )

    return frame


# --------------------------------------------------
# 5. APPLICATION
# --------------------------------------------------

def main():
    initialise_state()

    # Sidebar
    with st.sidebar:
        st.title("📊 BudgetClear")
        st.caption("Public Spending Reconciliation")
        st.divider()

        st.markdown("### Project")
        st.write("VORTEXA 3.0")
        st.write("Problem Statement G-03")

        st.divider()
        st.caption("Dashboard and Integration")

    # Header
    st.title("BudgetClear")
    st.subheader("Public Spending Reconciliation & Anomaly Review")

    st.info(DISCLAIMER)

    st.write(
        "Upload spending records, review data quality, compare "
        "declared budget totals, and inspect findings with supporting "
        "evidence."
    )

    # --------------------------------------------------
    # SECTION 1: INPUT
    # --------------------------------------------------

    st.divider()
    st.header("1. Load Spending Records")

    upload_column, sample_column = st.columns(2)

    with upload_column:
        uploaded_file = st.file_uploader(
            "Upload a CSV file",
            type=["csv"],
            help=(
                "Required columns: date, description, category, "
                "amount and reference."
            ),
        )

        if st.button(
            "Load Uploaded CSV",
            use_container_width=True,
        ):
            if uploaded_file is None:
                st.warning("Please select a CSV file first.")
            else:
                try:
                    st.session_state.transactions = (
                        prepare_uploaded_csv(uploaded_file)
                    )
                    st.session_state.input_source = (
                        uploaded_file.name
                    )
                    st.session_state.review_decisions = {}

                    st.success("CSV loaded successfully.")

                except Exception as error:
                    st.error(f"Unable to load CSV: {error}")

    with sample_column:
        st.markdown("**Try the built-in fictional dataset**")
        st.write(
            "This sample contains five records, including one "
            "transaction with a missing category."
        )

        st.button(
            "Load Demo Data",
            on_click=load_sample,
            use_container_width=True,
        )

    transactions = st.session_state.transactions

    if transactions is None:
        st.info(
            "Upload a CSV or click Load Demo Data to get started."
        )
        st.stop()

    # --------------------------------------------------
    # SECTION 2: DASHBOARD METRICS
    # --------------------------------------------------

    st.divider()
    st.header("2. Dashboard Overview")

    missing_category_mask = (
        transactions["category"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Transaction Records",
        len(transactions),
    )

    col2.metric(
        "Missing Categories",
        int(missing_category_mask.sum()),
    )

    col3.metric(
        "Input Source",
        "CSV" if st.session_state.input_source
        and st.session_state.input_source.endswith(".csv")
        else "Demo / Loaded Data",
    )

    # --------------------------------------------------
    # SECTION 3: TRANSACTION PREVIEW
    # --------------------------------------------------

    st.divider()
    st.header("3. Transaction Preview")

    st.caption(
        f"Loaded from: {st.session_state.input_source}"
    )

    st.dataframe(
        transactions,
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------
    # SECTION 4: DECLARED TOTALS
    # --------------------------------------------------

    st.divider()
    st.header("4. Declared Budget Totals")

    st.write(
        "Enter the totals stated in the budget report. "
        "The reconciliation module will compare these against "
        "the transaction records."
    )

    total_column, categories_column = st.columns(2)

    with total_column:
        stated_grand_total = st.text_input(
            "Stated Grand Total (₹)",
            value="29500.00",
        )

    with categories_column:
        stated_category_json = st.text_area(
            "Stated Category Totals (JSON)",
            value=json_lib.dumps(
                {
                    "Office Supplies": "2500.00",
                    "IT Equipment": "21500.00",
                    "Maintenance": "4000.00",
                },
                indent=2,
            ),
            height=150,
        )

    # --------------------------------------------------
    # SECTION 5: REVIEW AREAS
    # --------------------------------------------------

    st.divider()
    st.header("5. Findings and Review")

    verified_tab, quality_tab, ai_tab, review_tab = st.tabs(
    [
        "Verified Findings",
        "Data Quality & Duplicates",
        "AI Suggestions",
        "Human Review",
    ]
)
    # Verified reconciliation results
    with verified_tab:
        st.markdown("#### Rule-Based Reconciliation")

        if transactions is None or transactions.empty:
            st.info("Load transaction data to calculate reconciliation results.")
        else:
            try:
                records = transactions.to_dict(orient="records")

                # Decimal conversion from text avoids float-based money arithmetic.
                stated_total = st.text_input(
                    "Stated Grand Total (₹)",
                    value=str(stated_grand_total),
                    key="reconciliation_grand_total",
                )

                stated_categories = st.text_area(
                    "Stated Category Totals (JSON)",
                    value=stated_category_json,
                    key="reconciliation_category_totals",
                )

                from decimal import Decimal

                category_totals = json_lib.loads(stated_categories)

                findings = reconcile_budget(
                    records,
                    Decimal(stated_total),
                    {
                        name: Decimal(str(amount))
                        for name, amount in category_totals.items()
                    },
                )

                st.success("Reconciliation completed.")

                st.dataframe(findings, use_container_width=True)

            except (
                ValueError,
                TypeError,
                ArithmeticError,
                json_lib.JSONDecodeError,
            ) as exc:
                st.error(f"Unable to reconcile budget: {exc}")


    # Data quality
    with quality_tab:
        st.markdown("#### Data Quality Checks")

        missing_rows = transactions[
            missing_category_mask
        ]

        if missing_rows.empty:
            st.success("No missing categories found.")
        else:
            st.warning(
                f"{len(missing_rows)} transaction(s) have no category."
            )

            st.dataframe(
                missing_rows,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Missing categories are not automatically filled."
            )

        st.divider()

        st.markdown("#### Duplicate Detection")

        st.info(
            "Duplicate detection will be connected to "
            "modules/duplicate_detection.py."
        )


   
# AI suggestions
    with ai_tab:
     st.markdown("#### AI-Assisted Review")

    if st.session_state.transactions is None:
        st.info("Load demo data or upload a CSV file to see AI suggestions.")
    else:
        try:
            # Convert the current transaction DataFrame into records.
            ai_transactions = (
                st.session_state.transactions
                .fillna("")
                .to_dict(orient="records")
            )

            category_suggestions = suggest_categories(ai_transactions)
            anomaly_suggestions = suggest_anomalies(ai_transactions)

            st.caption(
                "AI outputs are suggestions for human review, "
                "not verified findings."
            )

            st.markdown("##### Category Suggestions")
            if category_suggestions:
                st.dataframe(
                    pd.DataFrame(category_suggestions),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("No category suggestions to review.")

            st.markdown("##### Unusual Transaction Suggestions")
            if anomaly_suggestions:
                st.dataframe(
                    pd.DataFrame(anomaly_suggestions),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("No unusual transaction suggestions to review.")

        except Exception as exc:
            st.error(f"Could not generate AI suggestions: {exc}")


    # Human review
    with review_tab:
        st.markdown("#### Suggestion Review Queue")

        st.info(
            "Accept and Reject controls will be added when the AI "
            "suggestion module is connected."
        )

        st.caption(
            "Accepted suggestions will affect a working copy only. "
            "The original uploaded records will remain unchanged."
        )

    # --------------------------------------------------
    # SECTION 6: EXPORT
    # --------------------------------------------------

    st.divider()
    st.header("6. Export Report")

    try:
        stated_category_totals = json_lib.loads(
            stated_category_json
        )

        if not isinstance(stated_category_totals, dict):
            raise ValueError(
                "Category totals must be a JSON object."
            )

        json_error = None

    except (json.JSONDecodeError, ValueError) as error:
        stated_category_totals = {}
        json_error = str(error)

    report = {
        "project": "BudgetClear",
        "problem_statement": "VORTEXA 3.0 G-03",
        "input_source": st.session_state.input_source,
        "transaction_count": len(transactions),
        "stated_grand_total": stated_grand_total,
        "stated_category_totals": stated_category_totals,
        "verified_findings": [],
        "data_quality_findings": [],
        "duplicate_findings": [],
        "ai_suggestions": [],
        "review_decisions": st.session_state.review_decisions,
        "disclaimer": DISCLAIMER,
        "status": (
            "Starter dashboard: connect the project modules "
            "to generate reconciliation findings."
        ),
    }

    if json_error:
        st.error(
            f"Please correct the category totals JSON: {json_error}"
        )

    export_column1, export_column2 = st.columns(2)

    with export_column1:
        st.download_button(
            label="Download Transaction CSV",
            data=transactions.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="budgetclear_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with export_column2:
        st.download_button(
            label="Download Starter JSON Report",
            data=json_lib.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            ).encode("utf-8"),
            file_name="budgetclear_report.json",
            mime="application/json",
            disabled=json_error is not None,
            use_container_width=True,
        )

    # Footer
    st.divider()

    st.caption(
        "BudgetClear | VORTEXA 3.0 | Fictional data for demonstration"
    )


# --------------------------------------------------
# 7. RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    main()
