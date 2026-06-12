import pandas as pd
import numpy as np


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Clean a DataFrame using a documented, deterministic pipeline:
      1. Strip whitespace from string columns
      2. Coerce numeric-looking string columns to numeric
      3. Fill missing values (median for numeric, mode for categorical)
      4. Remove exact duplicate rows

    Returns: (cleaned_df, report)

    report shape:
    {
      "cols_stripped": [...],
      "cols_coerced": [...],
      "nulls_filled": {col: count, ...},
      "fill_methods": {col: "median"|"mode", ...},
      "duplicates_removed": int,
      "rows_before": int,
      "rows_after": int,
    }
    """
    df = df.copy()
    report = {
        "cols_stripped": [],
        "cols_coerced": [],
        "nulls_filled": {},
        "fill_methods": {},
        "duplicates_removed": 0,
        "rows_before": len(df),
        "rows_after": None,
    }

    # ── Step 1: strip whitespace from string/object columns ──
    for col in df.select_dtypes(include="object").columns:
        original = df[col].copy()
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
        if not original.equals(df[col]):
            report["cols_stripped"].append(col)

    # ── Step 2: coerce numeric-looking object columns to numeric ──
    # A column is "numeric-looking" if, after stripping nulls,
    # at least 90% of non-null values can be parsed as numbers.
    for col in df.select_dtypes(include="object").columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        coerced = pd.to_numeric(non_null, errors="coerce")
        success_rate = coerced.notna().sum() / len(non_null)
        if success_rate >= 0.9:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            report["cols_coerced"].append(col)

    # ── Step 3: fill missing values ──
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        if null_count == 0:
            continue

        if pd.api.types.is_numeric_dtype(df[col]):
            fill_value = df[col].median()
            method = "median"
        else:
            mode_series = df[col].mode()
            fill_value = mode_series.iloc[0] if not mode_series.empty else "Unknown"
            method = "mode"

        df[col] = df[col].fillna(fill_value)
        report["nulls_filled"][col] = null_count
        report["fill_methods"][col] = method

    # ── Step 4: remove exact duplicate rows ──
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    after = len(df)
    report["duplicates_removed"] = before - after
    report["rows_after"] = after

    return df, report


def cleaning_summary_text(report: dict) -> list[str]:
    """Convert a cleaning report into plain-English bullet points
    for the chat / activity feed."""
    lines = []

    if report["cols_stripped"]:
        lines.append(f"Trimmed whitespace in {len(report['cols_stripped'])} column(s): {', '.join(report['cols_stripped'])}")

    if report["cols_coerced"]:
        lines.append(f"Converted {len(report['cols_coerced'])} column(s) to numeric: {', '.join(report['cols_coerced'])}")

    if report["nulls_filled"]:
        total_filled = sum(report["nulls_filled"].values())
        details = ", ".join(
            f"{col} ({count} via {report['fill_methods'][col]})"
            for col, count in report["nulls_filled"].items()
        )
        lines.append(f"Filled {total_filled} missing value(s): {details}")
    else:
        lines.append("No missing values to fill.")

    if report["duplicates_removed"] > 0:
        lines.append(f"Removed {report['duplicates_removed']} duplicate row(s).")
    else:
        lines.append("No duplicate rows found.")

    lines.append(f"Final shape: {report['rows_after']:,} rows (started with {report['rows_before']:,}).")

    return lines