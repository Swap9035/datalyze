import pandas as pd
import numpy as np


def detect_trends(df: pd.DataFrame) -> dict:
    """
    Detect trends in numeric columns.
    For datetime columns: rolling average + period-over-period % change.
    For numeric columns without datetime: overall trend direction.

    Returns per-column trend summary.
    """
    results = {}

    # ── Find datetime columns ─────────────────────────────────
    date_cols = [c for c in df.columns
                 if pd.api.types.is_datetime64_any_dtype(df[c])]

    # ── Try to parse object columns as datetime ───────────────
    for col in df.select_dtypes(include='object').columns:
        try:
            parsed = pd.to_datetime(df[col], errors='coerce')
            if parsed.notna().sum() > len(df) * 0.7:
                df[col] = parsed
                date_cols.append(col)
        except Exception:
            pass

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # ── Time-series trend (date + numeric) ────────────────────
    if date_cols and numeric_cols:
        date_col = date_cols[0]
        df_sorted = df.sort_values(date_col).copy()

        for num_col in numeric_cols[:5]:  # cap at 5 cols
            s = df_sorted[num_col].dropna()
            if len(s) < 4:
                continue

            # Rolling averages
            window_7  = min(7,  len(s) // 4)
            window_30 = min(30, len(s) // 2)
            rolling_7  = s.rolling(window_7,  min_periods=1).mean()
            rolling_30 = s.rolling(window_30, min_periods=1).mean()

            # Period-over-period % change
            # Split into first half vs second half
            mid    = len(s) // 2
            first  = float(s.iloc[:mid].mean())
            second = float(s.iloc[mid:].mean())
            pct_change = round(
                ((second - first) / first * 100) if first != 0 else 0, 2
            )

            # Trend direction
            direction = _classify_trend(pct_change)

            results[num_col] = {
                'type':            'time_series',
                'date_col':        date_col,
                'direction':       direction,
                'pct_change':      pct_change,
                'first_half_avg':  round(first, 4),
                'second_half_avg': round(second, 4),
                'rolling_7_last':  round(float(rolling_7.iloc[-1]), 4),
                'rolling_30_last': round(float(rolling_30.iloc[-1]), 4),
                'overall_min':     round(float(s.min()), 4),
                'overall_max':     round(float(s.max()), 4),
            }

    # ── Non-time-series: simple trend from index order ────────
    else:
        for num_col in numeric_cols[:5]:
            s = df[num_col].dropna().reset_index(drop=True)
            if len(s) < 10:
                continue

            # Linear regression slope (manual — no scipy needed)
            x    = np.arange(len(s))
            xm   = x.mean()
            ym   = float(s.mean())
            slope = float(
                ((x - xm) * (s - ym)).sum() /
                ((x - xm) ** 2).sum()
            ) if ((x - xm) ** 2).sum() != 0 else 0

            # Normalize slope as % of mean
            pct_change = round((slope * len(s) / ym * 100)
                               if ym != 0 else 0, 2)
            direction  = _classify_trend(pct_change)

            results[num_col] = {
                'type':       'linear',
                'direction':  direction,
                'slope':      round(slope, 6),
                'pct_change': pct_change,
                'mean':       round(ym, 4),
                'std':        round(float(s.std()), 4),
            }

    return results


def _classify_trend(pct_change: float) -> str:
    """Classify % change into trend direction."""
    if pct_change > 5:
        return 'up'
    elif pct_change < -5:
        return 'down'
    return 'flat'


def trend_summary_text(trend_results: dict) -> list[str]:
    """Plain-English bullet points about trends."""
    if not trend_results:
        return ["No trend data available — dataset may lack datetime columns."]

    lines = []
    for col, info in trend_results.items():
        direction = info['direction']
        pct       = info['pct_change']
        arrow     = '↑' if direction == 'up' else '↓' if direction == 'down' else '→'

        if info['type'] == 'time_series':
            lines.append(
                f"'{col}' trend: {arrow} {abs(pct)}% "
                f"({'increase' if direction == 'up' else 'decrease' if direction == 'down' else 'stable'}) "
                f"from first to second half of timeline."
            )
        else:
            lines.append(
                f"'{col}': {arrow} {abs(pct)}% overall trend "
                f"(slope: {info['slope']:+.4f} per row)."
            )

    return lines