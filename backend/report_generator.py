import pandas as pd
from datetime import datetime


def generate_markdown_report(
    filename:      str,
    profile:       dict,
    cleaning_report: dict,
    col_stats:     dict,
    outlier_iqr:   dict,
    outlier_zscore: dict,
    model_metrics: dict | None,
    feature_importance: list | None,
    trend_results: dict | None,
    insights:      list[str],
) -> str:
    """
    Generate a complete Markdown analysis report.
    All data is pre-computed — this function only formats it.
    """
    now   = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = []

    # ── Header ────────────────────────────────────────────────
    lines += [
        f"# Datalyze Analysis Report",
        f"",
        f"**File:** {filename}  ",
        f"**Generated:** {now}  ",
        f"**Rows:** {profile['rows']:,} · **Columns:** {profile['cols']}  ",
        f"**Data Quality Grade:** {profile['quality_grade']} "
        f"({profile['completeness_pct']}% complete)",
        f"",
        f"---",
        f"",
    ]

    # ── Quick insights ────────────────────────────────────────
    lines += ["## Quick Insights", ""]
    for insight in insights:
        lines.append(f"- {insight}")
    lines.append("")

    # ── Data cleaning ─────────────────────────────────────────
    lines += ["## Data Cleaning", ""]
    if cleaning_report:
        r = cleaning_report
        lines.append(f"- Whitespace trimmed in: "
                     f"{', '.join(r.get('cols_stripped', [])) or 'none'}")
        lines.append(f"- Columns coerced to numeric: "
                     f"{', '.join(r.get('cols_coerced', [])) or 'none'}")

        nulls = r.get('nulls_filled', {})
        if nulls:
            methods = r.get('fill_methods', {})
            for col, count in nulls.items():
                method = methods.get(col, 'unknown')
                lines.append(f"- `{col}`: {count} nulls filled via {method}")
        else:
            lines.append("- No missing values found")

        dupes = r.get('duplicates_removed', 0)
        lines.append(f"- Duplicate rows removed: {dupes}")
        lines.append(f"- Final shape: {r.get('rows_after', '?'):,} rows")
    lines.append("")

    # ── Column statistics ─────────────────────────────────────
    lines += ["## Column Statistics", ""]
    for col, stats in col_stats.items():
        kind = stats.get('kind', 'unknown')
        null_info = (f"{stats['null_count']} nulls ({stats['null_pct']}%)"
                     if stats['null_count'] > 0 else "no nulls")

        if kind == 'numeric':
            lines.append(
                f"**{col}** (numeric) — "
                f"mean: {stats.get('mean')}, "
                f"median: {stats.get('median')}, "
                f"std: {stats.get('std')}, "
                f"min: {stats.get('min')}, "
                f"max: {stats.get('max')}, "
                f"skew: {stats.get('skewness')}, "
                f"outliers: {stats.get('outlier_count')}, "
                f"{null_info}"
            )
        elif kind == 'categorical':
            top5 = stats.get('top_5', {})
            top_str = ', '.join(
                [f"'{k}'({v})" for k, v in list(top5.items())[:3]]
            )
            lines.append(
                f"**{col}** (categorical) — "
                f"{stats.get('unique_count')} unique, "
                f"top: {top_str}, "
                f"{null_info}"
            )
        elif kind == 'datetime':
            lines.append(
                f"**{col}** (datetime) — "
                f"{stats.get('min')} to {stats.get('max')}, "
                f"{stats.get('range_days')} days, "
                f"{null_info}"
            )
    lines.append("")

    # ── Outlier detection ─────────────────────────────────────
    lines += ["## Outlier Detection", ""]
    if outlier_iqr:
        total_iqr = sum(v['outlier_count'] for v in outlier_iqr.values())
        lines.append(f"**IQR method:** {total_iqr} outliers across "
                     f"{len(outlier_iqr)} columns")
        for col, info in outlier_iqr.items():
            lines.append(
                f"- `{col}`: {info['outlier_count']} outliers "
                f"(fence: {info['lower_fence']} – {info['upper_fence']}, "
                f"{info['high_count']}↑ {info['low_count']}↓)"
            )
    if outlier_zscore:
        total_z = sum(v['outlier_count'] for v in outlier_zscore.values())
        lines.append(f"\n**Z-score method (3σ):** {total_z} outliers across "
                     f"{len(outlier_zscore)} columns")
        for col, info in outlier_zscore.items():
            lines.append(
                f"- `{col}`: {info['outlier_count']} outliers"
            )
    lines.append("")

    # ── ML model ──────────────────────────────────────────────
    if model_metrics:
        lines += ["## ML Model — Logistic Regression", ""]
        lines.append(
            f"- Accuracy: **{model_metrics.get('accuracy')}%**  "
            f"Precision: {model_metrics.get('precision')}%  "
            f"Recall: {model_metrics.get('recall')}%  "
            f"F1: {model_metrics.get('f1')}%"
        )
        if feature_importance:
            lines.append("\n**Feature importance (top 5):**")
            for f in feature_importance[:5]:
                sign = '+' if f['coefficient'] > 0 else ''
                lines.append(
                    f"- `{f['feature']}`: {sign}{f['coefficient']} "
                    f"({'increases' if f['direction'] == 'positive' else 'decreases'} "
                    f"survival probability)"
                )
        lines.append("")

    # ── Trend analysis ────────────────────────────────────────
    if trend_results:
        lines += ["## Trend Analysis", ""]
        for col, info in trend_results.items():
            arrow = ('↑' if info['direction'] == 'up'
                     else '↓' if info['direction'] == 'down' else '→')
            lines.append(
                f"- **{col}**: {arrow} {abs(info['pct_change'])}% "
                f"({info['direction']})"
            )
        lines.append("")

    # ── Footer ────────────────────────────────────────────────
    lines += [
        "---",
        f"*Generated by Datalyze · {now}*",
    ]

    return "\n".join(lines)


def generate_csv_summary(
    profile:   dict,
    col_stats: dict,
    outlier_iqr: dict,
) -> str:
    """Generate a CSV summary of column-level stats."""
    rows = []
    for col, stats in col_stats.items():
        row = {
            'column':        col,
            'kind':          stats.get('kind'),
            'null_count':    stats.get('null_count'),
            'null_pct':      stats.get('null_pct'),
            'completeness':  stats.get('completeness'),
        }
        if stats.get('kind') == 'numeric':
            row.update({
                'mean':          stats.get('mean'),
                'median':        stats.get('median'),
                'std':           stats.get('std'),
                'min':           stats.get('min'),
                'max':           stats.get('max'),
                'skewness':      stats.get('skewness'),
                'outlier_count': stats.get('outlier_count'),
            })
        elif stats.get('kind') == 'categorical':
            row.update({
                'unique_count':   stats.get('unique_count'),
                'most_frequent':  stats.get('most_frequent'),
            })
        rows.append(row)

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)