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
    duplicate_count  = int(df.duplicated().sum())

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


def compute_column_stats(df: pd.DataFrame) -> dict:
    """
    Deep per-column statistics.
    Numeric  → mean, median, std, min, max, p25, p75, skewness, outlier_count (IQR)
    Categorical → top_5 value counts, unique count, most_frequent
    Datetime  → min, max, range_days
    All cols  → null_count, null_pct, completeness
    """
    stats = {}
    rows = len(df)

    for col in df.columns:
        col_stats = {
            'null_count': int(df[col].isnull().sum()),
            'null_pct': round(100 * df[col].isnull().sum() / rows, 2) if rows else 0,
            'completeness': round(100 * df[col].notna().sum() / rows, 2) if rows else 0,
        }

        # ── Numeric ──────────────────────────────────────────
        if pd.api.types.is_numeric_dtype(df[col]):
            s = df[col].dropna()
            if len(s) == 0:
                col_stats['kind'] = 'numeric'
                col_stats['note'] = 'all values missing'
                stats[col] = col_stats
                continue

            q1  = float(s.quantile(0.25))
            q3  = float(s.quantile(0.75))
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_count = int(((s < lower) | (s > upper)).sum())

            col_stats.update({
                'kind':          'numeric',
                'mean':          round(float(s.mean()), 4),
                'median':        round(float(s.median()), 4),
                'std':           round(float(s.std()), 4),
                'min':           round(float(s.min()), 4),
                'max':           round(float(s.max()), 4),
                'p25':           round(q1, 4),
                'p75':           round(q3, 4),
                'skewness':      round(float(s.skew()), 4),
                'outlier_count': outlier_count,
                'iqr_lower':     round(lower, 4),
                'iqr_upper':     round(upper, 4),
            })

        # ── Datetime ─────────────────────────────────────────
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            s = df[col].dropna()
            if len(s) == 0:
                col_stats['kind'] = 'datetime'
                stats[col] = col_stats
                continue

            col_stats.update({
                'kind':       'datetime',
                'min':        str(s.min()),
                'max':        str(s.max()),
                'range_days': int((s.max() - s.min()).days),
            })

        # ── Categorical / Boolean ─────────────────────────────
        else:
            s = df[col].dropna()
            value_counts = s.value_counts()
            top5 = value_counts.head(5)

            col_stats.update({
                'kind':           'categorical',
                'unique_count':   int(s.nunique()),
                'most_frequent':  str(value_counts.index[0]) if len(value_counts) else None,
                'most_freq_count':int(value_counts.iloc[0])  if len(value_counts) else 0,
                'most_freq_pct':  round(100 * value_counts.iloc[0] / len(s), 2) if len(s) else 0,
                'top_5': {
                    str(k): int(v) for k, v in top5.items()
                },
            })

        stats[col] = col_stats

    return stats


def quick_insights(df: pd.DataFrame, profile: dict) -> list[str]:
    """Generate plain-English findings about the dataset."""
    insights = []
    rows, cols = profile['rows'], profile['cols']

    insights.append(f"Dataset has {rows:,} rows and {cols} columns.")

    if profile['duplicate_count'] > 0:
        insights.append(f"{profile['duplicate_count']} duplicate row(s) detected.")

    if profile['total_nulls'] > 0:
        worst_col = max(profile['dtypes'].items(), key=lambda x: x[1]['nulls'])
        if worst_col[1]['nulls'] > 0:
            insights.append(
                f"'{worst_col[0]}' has the most nulls "
                f"({worst_col[1]['nulls']} missing, {worst_col[1]['null_pct']}%)."
            )
    else:
        insights.append("No missing values — dataset is complete.")

    cat_cols = [c for c, info in profile['dtypes'].items() if info['kind'] == 'categorical']
    if cat_cols:
        col = cat_cols[0]
        if df[col].notna().any():
            top_val   = df[col].mode().iloc[0]
            top_count = int((df[col] == top_val).sum())
            insights.append(
                f"Most common value in '{col}' is '{top_val}' ({top_count} occurrences)."
            )

    insights.append(
        f"Data quality grade: {profile['quality_grade']} ({profile['completeness_pct']}% complete)."
    )

    return insights


def build_context_for_llm(df: pd.DataFrame, profile: dict, col_stats: dict) -> str:
    """
    Build a compact text summary of the dataset to pass to the LLM.
    Keeps token usage low by including only the most relevant stats.
    The LLM narrates this — it does NOT compute it.
    """
    lines = [
        f"Dataset: {profile['rows']:,} rows × {profile['cols']} columns.",
        f"Quality grade: {profile['quality_grade']} ({profile['completeness_pct']}% complete).",
        f"Duplicates: {profile['duplicate_count']}.",
        "",
        "Column summary:",
    ]

    for col, s in col_stats.items():
        null_info = f"{s['null_count']} nulls" if s['null_count'] > 0 else "no nulls"

        if s['kind'] == 'numeric':
            lines.append(
                f"  [{col}] numeric — mean={s['mean']}, median={s['median']}, "
                f"std={s['std']}, min={s['min']}, max={s['max']}, "
                f"skew={s['skewness']}, outliers={s['outlier_count']}, {null_info}"
            )
        elif s['kind'] == 'categorical':
            top = ', '.join([f"'{k}'({v})" for k, v in list(s['top_5'].items())[:3]])
            lines.append(
                f"  [{col}] categorical — {s['unique_count']} unique, "
                f"top: {top}, {null_info}"
            )
        elif s['kind'] == 'datetime':
            lines.append(
                f"  [{col}] datetime — {s.get('min','?')} to {s.get('max','?')}, "
                f"range={s.get('range_days','?')} days, {null_info}"
            )

    return "\n".join(lines)