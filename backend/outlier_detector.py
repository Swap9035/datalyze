import pandas as pd
import numpy as np


def detect_outliers_iqr(df: pd.DataFrame) -> dict:
    """
    IQR method: flag values below Q1 - 1.5*IQR or above Q3 + 1.5*IQR.
    Robust to non-normal distributions — preferred for skewed data.

    Returns per-column summary + flagged row indices.
    """
    results = {}

    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) == 0:
            continue

        q1  = float(s.quantile(0.25))
        q3  = float(s.quantile(0.75))
        iqr = q3 - q1

        if iqr == 0:
            continue  # constant column — skip

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outlier_mask  = (df[col] < lower) | (df[col] > upper)
        outlier_rows  = df[outlier_mask][[col]].copy()
        outlier_rows  = outlier_rows.rename(columns={col: 'value'})
        outlier_rows['direction'] = outlier_rows['value'].apply(
            lambda v: 'high' if v > upper else 'low'
        )

        if len(outlier_rows) == 0:
            continue

        results[col] = {
            'method':        'IQR',
            'q1':            round(q1, 4),
            'q3':            round(q3, 4),
            'iqr':           round(iqr, 4),
            'lower_fence':   round(lower, 4),
            'upper_fence':   round(upper, 4),
            'outlier_count': len(outlier_rows),
            'pct_of_col':    round(100 * len(outlier_rows) / len(s), 2),
            'top_values':    [
                round(float(v), 4)
                for v in outlier_rows['value']
                .abs()
                .nlargest(5)
                .index
                .map(lambda i: outlier_rows.loc[i, 'value'])
            ] if len(outlier_rows) > 0 else [],
            'high_count':    int((outlier_rows['direction'] == 'high').sum()),
            'low_count':     int((outlier_rows['direction'] == 'low').sum()),
            'row_indices':   outlier_rows.index.tolist()[:20],  # cap at 20
        }

    return results


def detect_outliers_zscore(df: pd.DataFrame, threshold: float = 3.0) -> dict:
    """
    Z-score method: flag values where |z| > threshold (default 3.0).
    Best for normally distributed data.
    Complements IQR — use both and compare.

    Returns per-column summary.
    """
    results = {}

    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) < 3:
            continue

        mean = float(s.mean())
        std  = float(s.std())

        if std == 0:
            continue  # constant column — skip

        z_scores     = (s - mean) / std
        outlier_mask = z_scores.abs() > threshold
        outlier_vals = s[outlier_mask]

        if len(outlier_vals) == 0:
            continue

        results[col] = {
            'method':        'z-score',
            'threshold':     threshold,
            'mean':          round(mean, 4),
            'std':           round(std, 4),
            'outlier_count': int(len(outlier_vals)),
            'pct_of_col':    round(100 * len(outlier_vals) / len(s), 2),
            'top_values':    [round(float(v), 4) for v in outlier_vals.abs().nlargest(5).index.map(lambda i: outlier_vals.loc[i])],
            'row_indices':   outlier_vals.index.tolist()[:20],
        }

    return results


def compare_methods(
    iqr_results: dict,
    zscore_results: dict
) -> list[dict]:
    """
    Side-by-side comparison of IQR vs z-score per column.
    Highlights columns where the two methods disagree significantly —
    useful interview talking point about method sensitivity.
    """
    all_cols = set(iqr_results.keys()) | set(zscore_results.keys())
    comparison = []

    for col in sorted(all_cols):
        iqr_count = iqr_results.get(col, {}).get('outlier_count', 0)
        z_count   = zscore_results.get(col, {}).get('outlier_count', 0)
        diff      = abs(iqr_count - z_count)

        comparison.append({
            'column':        col,
            'iqr_count':     iqr_count,
            'zscore_count':  z_count,
            'difference':    diff,
            'agreement':     'high' if diff <= 2 else 'low',
            'note': (
                f"IQR finds {iqr_count - z_count} more — data may be skewed"
                if iqr_count > z_count else
                f"Z-score finds {z_count - iqr_count} more — data may be near-normal"
                if z_count > iqr_count else
                "Both methods agree"
            )
        })

    return comparison


def outlier_summary_text(
    iqr_results: dict,
    zscore_results: dict
) -> list[str]:
    """
    Plain-English bullet points about outliers.
    Passed to Gemini on Day 9 as pre-computed findings.
    """
    lines = []

    if not iqr_results and not zscore_results:
        lines.append("No outliers detected in any numeric column.")
        return lines

    total_iqr    = sum(r['outlier_count'] for r in iqr_results.values())
    total_zscore = sum(r['outlier_count'] for r in zscore_results.values())
    lines.append(
        f"IQR method detected {total_iqr} outlier(s) across "
        f"{len(iqr_results)} column(s)."
    )
    lines.append(
        f"Z-score method (threshold=3σ) detected {total_zscore} outlier(s) "
        f"across {len(zscore_results)} column(s)."
    )

    # Per-column detail for top 3 most affected columns
    top_cols = sorted(
        iqr_results.items(),
        key=lambda x: x[1]['outlier_count'],
        reverse=True
    )[:3]

    for col, info in top_cols:
        lines.append(
            f"'{col}': {info['outlier_count']} outliers via IQR "
            f"(fence: {info['lower_fence']} – {info['upper_fence']}), "
            f"{info['high_count']} high / {info['low_count']} low."
        )

    comparison = compare_methods(iqr_results, zscore_results)
    low_agree  = [c for c in comparison if c['agreement'] == 'low']
    if low_agree:
        cols_str = ', '.join(c['column'] for c in low_agree)
        lines.append(
            f"Methods disagree on: {cols_str} — "
            f"suggests skewed distribution in these columns."
        )

    return lines