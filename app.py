
def prepare_uploaded_csv(uploaded_file):
    """Load standard transaction CSVs or public expenditure datasets."""
    frame = pd.read_csv(
        uploaded_file,
        dtype=str,
        keep_default_na=False,
    )

    # Normalize headers while preserving meaningful punctuation.
    frame.columns = [
        str(column).strip().lstrip("\ufeff").lower().strip().replace(" ", "_")
        for column in frame.columns
    ]

    if frame.empty:
        raise ValueError("The CSV contains no data rows.")

    # --------------------------------------------------
    # Format 1: Public expenditure dataset
    # --------------------------------------------------
    expenditure_columns = {
        "year",
        "country",
        "sector",
        "expenditure(million_usd)",
        "gdp(%)",
    }

    if expenditure_columns.issubset(set(frame.columns)):
        # Remove an automatically exported index column, if present.
        frame = frame.drop(
            columns=[
                column
                for column in frame.columns
                if column.startswith("unnamed:")
            ],
            errors="ignore",
        )

        # These are country/year/sector records, not payment transactions.
        frame["transaction_id"] = [
            f"EXP-{i:06d}" for i in range(1, len(frame) + 1)
        ]

        frame["date"] = frame["year"].astype(str).str.strip().apply(
            lambda year: f"{year}-01-01" if year else ""
        )

        frame["description"] = (
            frame["country"].astype(str).str.strip()
            + " - "
            + frame["sector"].astype(str).str.strip()
        ).str.strip(" -")

        frame["category"] = frame["sector"].astype(str).str.strip()
        frame["amount"] = (
            frame["expenditure(million_usd)"].astype(str).str.strip()
        )

        frame["reference"] = [
            f"WORLD-EXP-{i:06d}" for i in range(1, len(frame) + 1)
        ]

        # Preserve the original units and GDP percentage.
        frame["amount_unit"] = "million USD"
        frame["dataset_type"] = "public_expenditure"
        frame["gdp_percent"] = frame["gdp(%)"].astype(str).str.strip()

        return frame

    # --------------------------------------------------
    # Format 2: Existing standard transaction CSV
    # --------------------------------------------------
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
            "Unsupported CSV format. Standard transaction CSVs require "
            "date, description, category, amount and reference. "
            "Public expenditure CSVs require Year, Country, Sector, "
            "Expenditure(million USD) and GDP(%). Missing transaction "
            "columns: " + ", ".join(missing)
        )

    if "transaction_id" not in frame.columns:
        frame.insert(
            0,
            "transaction_id",
            [f"TXN-{i:03d}" for i in range(1, len(frame) + 1)],
        )

    frame["amount_unit"] = "INR"
    frame["dataset_type"] = "transactions"

    return frame
