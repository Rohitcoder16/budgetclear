
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation

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

DISCLAIMER = (
    "An anomaly flag is not proof of corruption or wrongdoing. "
    "Every flag requires human investigation."
)

SAMPLE_DATA = [
    {"transaction_id": "TXN-001", "date": "2026-09-01",
     "description": "Office stationery", "category": "Office Supplies",
     "amount": "2500.00", "reference": "REF-101"},
    {"transaction_id": "TXN-002", "date": "2026-09-02",
     "description": "Computer equipment", "category": "IT Equipment",
     "amount": "18500.00", "reference": "REF-102"},
    {"transaction_id": "TXN-003", "date": "2026-09-03",
     "description": "Office cleaning", "category": "Maintenance",
     "amount": "4000.00", "reference": "REF-103"},
    {"transaction_id": "TXN-004", "date": "2026-09-04",
     "description": "Office stationery supplies", "category": "",
     "amount": "1500.00", "reference": "REF-104"},
    {"transaction_id": "TXN-005", "date": "2026-09-05",
     "description": "IT accessories", "category": "IT Equipment",
     "amount": "3000.00", "reference": "REF-105"},
]

DEFAULT_TOTALS = {
    "Office Supplies": "2500.00",
    "IT Equipment": "21500.00",
    "Maintenance": "4000.00",
}


st.markdown("""
<style>
.block-container {
    max-width: 1450px;
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(120,130,150,.2);
}
.hero {
    padding: 28px;
    border-radius: 16px;
    color: white;
    background: linear-gradient(120deg,#14253d,#203e5e,#23645e);
    margin-bottom: 16px;
}
.hero h1 { color: white; margin-bottom: 6px; }
.hero p { color: #e0eaf3; margin-bottom: 0; }
div[data-testid="stMetric"] {
    border: 1px solid rgba(120,130,150,.2);
    padding: 16px;
    border-radius: 12px;
}
div.stButton > button, div.stDownloadButton > button {
    border-radius: 9px;
    min-height: 40px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


def safe_amount(value):
    try:
        amount = Decimal(str(value).strip())
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def money(value):
    return f"₹{value:,.2f}"


def load_demo():
    st.session_state.transactions = pd.DataFrame(
        deepcopy(SAMPLE_DATA)
    )
    st.session_state.input_source = "Fictional demo data"
    st.session_state.review_decisions = {}


def prepare_csv(uploaded_file):
    df = pd.read_csv(
        uploaded_file,
        dtype=str,
        keep_default_na=False,
    )
    df.columns = [
        str(c).strip().lstrip("\ufeff").lower().replace(" ", "_")
        for c in df.columns
    ]

    if df.empty:
        raise ValueError("The CSV has no data rows.")

    expenditure_columns = {
        "year", "country", "sector",
        "expenditure(million_usd)", "gdp(%)"
    }

    if expenditure_columns.issubset(df.columns):
        df["transaction_id"] = [
            f"EXP-{i:06d}" for i in range(1, len(df) + 1)
        ]
        df["date"] = df["year"].apply(
            lambda y: f"{y}-01-01" if str(y).strip() else ""
        )
        df["description"] = (
            df["country"].astype(str) + " - " + df["sector"].astype(str)
        )
        df["category"] = df["sector"]
        df["amount"] = df["expenditure(million_usd)"]
        df["reference"] = [
            f"WORLD-EXP-{i:06d}" for i in range(1, len(df) + 1)
        ]
        df["amount_unit"] = "million USD"
        df["dataset_type"] = "public_expenditure"
        df["gdp_percent"] = df["gdp(%)"]
        return df

    required = ["date", "description", "category", "amount", "reference"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            "Required transaction columns missing: " + ", ".join(missing)
        )

    if "transaction_id" not in df.columns:
        df.insert(
            0, "transaction_id",
            [f"TXN-{i:03d}" for i in range(1, len(df) + 1)]
        )

    df["amount_unit"] = "INR"
    df["dataset_type"] = "transactions"
    return df


def show_findings(items, empty_message):
    if not items:
        st.info(empty_message)
        return

    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            st.write(item)
            continue

        title = (
            item.get("title")
            or item.get("finding_type")
            or item.get("transaction_id")
            or f"Finding {i}"
        )
        message = (
            item.get("message")
            or item.get("reason")
            or item.get("description")
            or ""
        )

        with st.container(border=True):
            st.markdown(f"**{title}**")
            if message:
                st.write(message)

            severity = item.get("severity")
            source = item.get("source")
            evidence = (
                item.get("evidence_transaction_ids")
                or item.get("evidence_ids")
            )

            if severity:
                st.caption(f"Severity: {severity}")
            if source:
                st.caption(f"Source: {source}")
            if item.get("transaction_id"):
                st.caption(f"Transaction: {item['transaction_id']}")
            if evidence:
                st.caption("Evidence IDs: " + ", ".join(map(str, evidence)))

            difference = item.get("amount_difference")
            if difference is not None:
                parsed = safe_amount(difference)
                if parsed is not None:
                    st.caption(f"Amount difference: {money(parsed)}")


def call_module(label, function, *args):
    try:
        result = function(*args)
        return result if result is not None else [], None
    except Exception as exc:
        return [], f"{label}: {exc}"


def main():
    for key, value in {
        "transactions": None,
        "input_source": None,
        "review_decisions": {},
    }.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:12px;padding:8px 0 18px">
          <div style="font-size:28px;background:#203B51;border-radius:10px;padding:8px">📊</div>
          <div>
            <div style="font-size:23px;font-weight:750">BudgetClear</div>
            <div style="font-size:10px;letter-spacing:1px;color:#94A3B8">
              PUBLIC SPENDING ANALYTICS
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.caption("WORKSPACE")
        st.markdown("""
        <div style="padding:10px;background:rgba(76,139,196,.17);
        border-left:3px solid #60A5FA;border-radius:8px;font-weight:600">
        ▦ &nbsp; Dashboard
        </div>
        <div style="padding:10px;color:#94A3B8;line-height:2.2">
        ▤ &nbsp; Data &amp; Validation<br>
        ⚖ &nbsp; Reconciliation<br>
        ⌕ &nbsp; Anomaly Review<br>
        ☑ &nbsp; Human Review<br>
        ⇩ &nbsp; Reports &amp; Exports
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        st.caption("Analysis supports investigation; findings require human review.")

    # Header
    st.markdown("""
    <div class="hero">
      <h1>BudgetClear</h1>
      <p>Public Spending Reconciliation &amp; Anomaly Review</p>
    </div>
    """, unsafe_allow_html=True)

    st.warning(DISCLAIMER)

    # Load data
    st.header("1. Load spending records")
    upload_col, demo_col = st.columns(2)

    with upload_col:
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if st.button("Load uploaded CSV", type="primary", use_container_width=True):
            if uploaded is None:
                st.warning("Choose a CSV file first.")
            else:
                try:
                    uploaded.seek(0)
                    st.session_state.transactions = prepare_csv(uploaded)
                    st.session_state.input_source = uploaded.name
                    st.session_state.review_decisions = {}
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not load CSV: {exc}")

    with demo_col:
        st.write("Explore the dashboard using fictional sample records.")
        st.button("Load demo data", on_click=load_demo, use_container_width=True)

    if st.session_state.transactions is None:
        st.info("Upload a CSV or load demo data to begin.")
        st.stop()

    original_df = st.session_state.transactions.copy(deep=True)
    records = original_df.fillna("").astype(str).to_dict("records")

    # Validate first
    validation, validation_error = call_module(
        "Validation failed", validate_transactions, records
    )
    normalized = validation.get("normalized_transactions", records)
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])

    missing_categories = int(
        original_df["category"].fillna("").astype(str).str.strip().eq("").sum()
    )
    missing_amounts = int(
        original_df["amount"].fillna("").astype(str).str.strip().eq("").sum()
    )

    total = Decimal("0.00")
    valid_count = 0
    invalid_count = 0
    for row in normalized:
        amount = safe_amount(row.get("amount"))
        if amount is None:
            invalid_count += 1
        else:
            total += amount
            valid_count += 1

    # Overview
    st.divider()
    st.header("2. Dashboard overview")
    st.caption(f"Source: {st.session_state.input_source}")

    a, b, c = st.columns(3)
    a.metric("Transactions", f"{len(original_df):,}")
    b.metric("Recorded amount total", money(total))
    c.metric("Validation errors", len(errors))

    d, e, f = st.columns(3)
    d.metric("Missing categories", missing_categories)
    e.metric("Missing amounts", missing_amounts)
    f.metric("Validation warnings", len(warnings))

    if invalid_count:
        st.warning(f"{invalid_count} amount(s) could not be parsed.")

    with st.expander("Preview original transactions", expanded=True):
        st.dataframe(original_df, use_container_width=True, hide_index=True)

    # Charts
    st.subheader("Spending analytics")
    is_public = (
        "dataset_type" in original_df.columns
        and original_df["dataset_type"].eq("public_expenditure").all()
    )
    unit = "million USD" if is_public else "INR"

    category_totals = {}
    date_totals = {}

    for row in normalized:
        amount = safe_amount(row.get("amount"))
        if amount is None:
            continue

        category = str(row.get("category") or "").strip() or "Uncategorized"
        category_totals[category] = category_totals.get(
            category, Decimal("0")
        ) + amount

        date_value = pd.to_datetime(row.get("date"), errors="coerce")
        if not pd.isna(date_value):
            day = date_value.strftime("%Y-%m-%d")
            date_totals[day] = date_totals.get(day, Decimal("0")) + amount

    chart1, chart2 = st.columns(2, gap="large")
    with chart1:
        with st.container(border=True):
            st.markdown("#### Spending by category")
            if category_totals:
                chart_df = pd.DataFrame([
                    {"Category": k, "Amount": float(v)}
                    for k, v in sorted(category_totals.items(), key=lambda x: x[1])
                ])
                st.bar_chart(
                    chart_df, x="Category", y="Amount",
                    horizontal=True, height=max(260, 55 * len(chart_df))
                )
            else:
                st.info("No valid amounts to chart.")

    with chart2:
        with st.container(border=True):
            st.markdown("#### Spending over time")
            if date_totals:
                trend_df = pd.DataFrame([
                    {"Date": pd.to_datetime(k), "Amount": float(v)}
                    for k, v in sorted(date_totals.items())
                ])
                st.line_chart(trend_df, x="Date", y="Amount", height=320)
            else:
                st.info("No valid dated amounts to chart.")

    st.caption(f"Chart amounts are recorded in {unit}; charts are not proof of wrongdoing.")

    # Declared totals
    st.divider()
    st.header("3. Declared budget totals")
    st.caption("Enter the totals stated in the source budget. Demo amounts are examples.")

    stated_total = st.text_input(
        f"Stated grand total ({unit})", value="29500.00", key="grand_total"
    )

    categories = dict(DEFAULT_TOTALS)
    st.markdown("#### Category totals")
    category_cols = st.columns(2)

    for i, (category, default) in enumerate(DEFAULT_TOTALS.items()):
        with category_cols[i % 2]:
            categories[category] = st.text_input(
                f"{category} ({unit})", value=default,
                key=f"budget_{category}"
            )

    with st.expander("Add another category"):
        extra_name = st.text_input("Category name", key="extra_category")
        extra_amount = st.text_input("Declared amount", value="0.00", key="extra_amount")
        if extra_name.strip():
            categories[extra_name.strip()] = extra_amount

    # Rule-based analysis and AI are kept separate
    reconciliation, recon_error = call_module(
        "Reconciliation failed", reconcile_budget,
        normalized, stated_total, categories
    )
    duplicates, duplicate_error = call_module(
        "Duplicate detection failed", detect_duplicates, normalized
    )
    suggestions, suggestion_error = call_module(
        "Category suggestions failed", suggest_categories, normalized
    )
    anomalies, anomaly_error = call_module(
        "AI anomaly analysis failed", suggest_anomalies, normalized
    )

    # Findings
    st.divider()
    st.header("4. Findings and review")

    verified_tab, quality_tab, ai_tab, review_tab = st.tabs([
        "Verified findings", "Data quality & duplicates",
        "AI suggestions", "Human review"
    ])

    with verified_tab:
        st.subheader("Rule-based reconciliation")
        if recon_error:
            st.error(recon_error)
        else:
            show_findings(reconciliation, "No reconciliation findings returned.")

    with quality_tab:
        st.subheader("Validation errors")
        if validation_error:
            st.error(validation_error)
        show_findings(errors, "No validation errors reported.")

        st.subheader("Validation warnings")
        show_findings(warnings, "No validation warnings reported.")

        st.subheader("Potential duplicates")
        if duplicate_error:
            st.error(duplicate_error)
        show_findings(duplicates, "No duplicate candidates returned.")

        missing_rows = original_df[
            original_df["category"].fillna("").astype(str).str.strip().eq("")
        ]
        st.subheader("Records with missing categories")
        if missing_rows.empty:
            st.success("No missing categories.")
        else:
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

    with ai_tab:
        st.subheader("Category suggestions")
        if suggestion_error:
            st.error(suggestion_error)
        show_findings(suggestions, "No category suggestions returned.")

        st.subheader("Potential anomalies")
        if anomaly_error:
            st.error(anomaly_error)
        show_findings(anomalies, "No potential anomalies returned.")

        st.caption("AI suggestions are advisory and require human review.")

    # Human review changes only a working copy
    with review_tab:
        st.subheader("Review category suggestions")

        if suggestion_error:
            st.error(suggestion_error)
        elif not suggestions:
            st.info("No category suggestions to review.")
        else:
            for i, item in enumerate(suggestions):
                if not isinstance(item, dict):
                    continue

                txn_id = str(item.get("transaction_id", ""))
                proposed = str(item.get("suggested_category") or "").strip()
                key = f"category:{txn_id}"
                status = st.session_state.review_decisions.get(key, "pending")

                with st.container(border=True):
                    st.markdown(f"**Transaction: {txn_id or 'Unknown'}**")
                    st.write(f"Suggested category: {proposed or 'No suggestion'}")
                    if item.get("reason"):
                        st.caption(str(item["reason"]))
                    if item.get("confidence") is not None:
                        st.caption(f"Confidence: {item['confidence']}")
                    st.caption(f"Status: {status.title()}")

                    accept_col, reject_col = st.columns(2)
                    with accept_col:
                        if st.button(
                            "Accept", key=f"accept_{i}_{txn_id}",
                            disabled=not proposed or status == "accepted",
                            use_container_width=True
                        ):
                            st.session_state.review_decisions[key] = "accepted"
                            st.rerun()

                    with reject_col:
                        if st.button(
                            "Reject", key=f"reject_{i}_{txn_id}",
                            disabled=status == "rejected",
                            use_container_width=True
                        ):
                            st.session_state.review_decisions[key] = "rejected"
                            st.rerun()

    reviewed = deepcopy(normalized)
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        txn_id = str(item.get("transaction_id", ""))
        proposed = str(item.get("suggested_category") or "").strip()

        if (
            proposed
            and st.session_state.review_decisions.get(f"category:{txn_id}") == "accepted"
        ):
            for row in reviewed:
                if (
                    str(row.get("transaction_id", "")) == txn_id
                    and not str(row.get("category", "")).strip()
                ):
                    row["category"] = proposed

    # Export
    st.divider()
    st.header("5. Export reports")

    module_errors = {
        "validation": validation_error,
        "reconciliation": recon_error,
        "duplicates": duplicate_error,
        "category_suggestions": suggestion_error,
        "anomaly_analysis": anomaly_error,
    }

    report = {
        "project": "BudgetClear",
        "input_source": st.session_state.input_source,
        "transaction_count": len(original_df),
        "recorded_amount_total": str(total),
        "amount_unit": unit,
        "stated_grand_total": stated_total,
        "stated_category_totals": categories,
        "verified_findings": reconciliation,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "duplicate_findings": duplicates,
        "ai_category_suggestions": suggestions,
        "ai_anomaly_suggestions": anomalies,
        "review_decisions": st.session_state.review_decisions,
        "original_transactions": records,
        "reviewed_transactions": reviewed,
        "module_errors": module_errors,
        "disclaimer": DISCLAIMER,
    }

    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "Download original CSV",
            original_df.to_csv(index=False).encode("utf-8"),
            "budgetclear_original.csv",
            "text/csv",
            use_container_width=True,
        )

    with col2:
        st.download_button(
            "Download reviewed CSV",
            pd.DataFrame(reviewed).to_csv(index=False).encode("utf-8"),
            "budgetclear_reviewed.csv",
            "text/csv",
            use_container_width=True,
        )

    with col3:
        st.download_button(
            "Download JSON report",
            json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
            "budgetclear_report.json",
            "application/json",
            use_container_width=True,
        )

    st.caption(
        "Original records are preserved. Accepted suggestions affect only "
        "the reviewed copy. Every flag requires human investigation."
    )


if __name__ == "__main__":
    main()
