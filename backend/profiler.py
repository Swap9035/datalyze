import pandas as pd
import numpy as np


def load_dataframe(file_path: str, filename: str) -> pd.DataFrame:
    """Load a CSV, Excel, or JSON file into a pandas DataFrame."""
    ext = filename.lower().split('.')[-1]

    if ext == 'csv':
        df = pd.read_csv(file_path)
    elif ext in ('xlsx', 'xls'):
        df = pd.read_excel(file_path)
    elif ext == 'json':
        df = pd.read_json(file_path)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    return df


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Generate a schema + quality summary for a DataFrame."""
    rows, cols = df.shape

    null_counts = df.isnull().sum()
    total_nulls = int(null_counts.sum())
    total_cells = rows * cols if rows * cols > 0 else 1
    completeness_pct = round(100 * (1 - total_nulls / total_cells), 2)

    duplicate_count = int(df.duplicated().sum())

    # Column type breakdown
    dtypes = {}
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        if pd.api.types.is_numeric_dtype(df[col]):
            kind = 'numeric'
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            kind = 'datetime'
        elif pd.api.types.is_bool_dtype(df[col]):
            kind = 'boolean'
        else:
            kind = 'categorical'
        dtypes[col] = {
            'dtype': dtype_str,
            'kind': kind,
            'nulls': int(null_counts[col]),
            'null_pct': round(100 * null_counts[col] / rows, 2) if rows else 0,
        }

    # Data quality grade
    if completeness_pct >= 98:
        grade = 'A'
    elif completeness_pct >= 90:
        grade = 'B'
    elif completeness_pct >= 75:
        grade = 'C'
    else:
        grade = 'D'

    return {
        'rows': rows,
        'cols': cols,
        'columns': list(df.columns),
        'dtypes': dtypes,
        'total_nulls': total_nulls,
        'completeness_pct': completeness_pct,
        'quality_grade': grade,
        'duplicate_count': duplicate_count,
    }


def quick_insights(df: pd.DataFrame, profile: dict) -> list[str]:
    """Generate 3-5 plain-English findings about the dataset."""
    insights = []
    rows, cols = profile['rows'], profile['cols']

    insights.append(f"Dataset has {rows:,} rows and {cols} columns.")

    if profile['duplicate_count'] > 0:
        insights.append(f"{profile['duplicate_count']} duplicate row(s) detected.")

    if profile['total_nulls'] > 0:
        worst_col = max(profile['dtypes'].items(), key=lambda x: x[1]['nulls'])
        if worst_col[1]['nulls'] > 0:
            insights.append(
                f"'{worst_col[0]}' has the most missing values "
                f"({worst_col[1]['nulls']} nulls, {worst_col[1]['null_pct']}%)."
            )
    else:
        insights.append("No missing values found — dataset is complete.")

    # Most frequent category in first categorical column
    cat_cols = [c for c, info in profile['dtypes'].items() if info['kind'] == 'categorical']
    if cat_cols:
        col = cat_cols[0]
        if df[col].notna().any():
            top_val = df[col].mode().iloc[0]
            top_count = int((df[col] == top_val).sum())
            insights.append(f"Most common value in '{col}' is '{top_val}' ({top_count} occurrences).")

    insights.append(f"Data quality grade: {profile['quality_grade']} ({profile['completeness_pct']}% complete).")

    return insights