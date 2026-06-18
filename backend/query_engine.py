import pandas as pd
import numpy as np


def run_query(df: pd.DataFrame, action: dict) -> dict:
    """
    Execute a structured action on a DataFrame.
    Action shapes:
      {"type": "top_n",      "column": "Fare",      "n": 10}
      {"type": "filter_by",  "column": "Sex",        "value": "female"}
      {"type": "group_by",   "column": "Pclass",     "agg_col": "Survived", "agg": "mean"}
      {"type": "correlation", "col1": "Age",         "col2": "Fare"}
      {"type": "summary",    "column": "Age"}
      {"type": "value_counts","column": "Sex"}
      {"type": "date_range", "column": "date_col"}
    """
    action_type = action.get("type", "summary")

    try:
        if action_type == "top_n":
            return _top_n(df, action)
        elif action_type == "filter_by":
            return _filter_by(df, action)
        elif action_type == "group_by":
            return _group_by(df, action)
        elif action_type == "correlation":
            return _correlation(df, action)
        elif action_type == "summary":
            return _summary(df, action)
        elif action_type == "value_counts":
            return _value_counts(df, action)
        elif action_type == "date_range":
            return _date_range(df, action)
        else:
            return {"type": "error", "message": f"Unknown action: {action_type}"}

    except Exception as e:
        return {"type": "error", "message": str(e)}


def _top_n(df: pd.DataFrame, action: dict) -> dict:
    col = action.get("column")
    n   = int(action.get("n", 10))

    if col not in df.columns:
        return {"type": "error", "message": f"Column '{col}' not found"}

    result = df.nlargest(n, col)[[col]].reset_index()
    return {
        "type":    "top_n",
        "column":  col,
        "n":       n,
        "data":    result.to_dict(orient="records"),
        "x_col":   "index",
        "y_col":   col,
        "chart_suggestion": "bar",
    }


def _filter_by(df: pd.DataFrame, action: dict) -> dict:
    col   = action.get("column")
    value = action.get("value")

    if col not in df.columns:
        return {"type": "error", "message": f"Column '{col}' not found"}

    filtered = df[df[col].astype(str).str.lower() == str(value).lower()]
    return {
        "type":          "filter_by",
        "column":        col,
        "value":         value,
        "matched_rows":  len(filtered),
        "total_rows":    len(df),
        "pct":           round(100 * len(filtered) / len(df), 2),
        "chart_suggestion": None,
    }


def _group_by(df: pd.DataFrame, action: dict) -> dict:
    col     = action.get("column")
    agg_col = action.get("agg_col")
    agg     = action.get("agg", "mean")

    if col not in df.columns:
        return {"type": "error", "message": f"Column '{col}' not found"}
    if agg_col not in df.columns:
        return {"type": "error", "message": f"Agg column '{agg_col}' not found"}

    grouped = df.groupby(col)[agg_col].agg(agg).reset_index()
    grouped.columns = [col, f"{agg}_{agg_col}"]
    grouped = grouped.round(4)

    return {
        "type":     "group_by",
        "column":   col,
        "agg_col":  agg_col,
        "agg":      agg,
        "data":     grouped.to_dict(orient="records"),
        "x_col":    col,
        "y_col":    f"{agg}_{agg_col}",
        "chart_suggestion": "bar",
    }


def _correlation(df: pd.DataFrame, action: dict) -> dict:
    col1 = action.get("col1")
    col2 = action.get("col2")

    numeric_df = df.select_dtypes(include=[np.number])

    if col1 and col2:
        # Single pair
        if col1 not in numeric_df.columns or col2 not in numeric_df.columns:
            return {"type": "error",
                    "message": f"Both columns must be numeric"}
        corr = round(float(numeric_df[col1].corr(numeric_df[col2])), 4)
        return {
            "type":   "correlation",
            "col1":   col1,
            "col2":   col2,
            "value":  corr,
            "strength": _corr_strength(corr),
            "chart_suggestion": "scatter",
        }
    else:
        # Full matrix
        corr_matrix = numeric_df.corr().round(4)
        return {
            "type":             "correlation_matrix",
            "columns":          list(corr_matrix.columns),
            "matrix":           corr_matrix.to_dict(),
            "chart_suggestion": "heatmap",
        }


def _summary(df: pd.DataFrame, action: dict) -> dict:
    col = action.get("column")

    if col and col in df.columns:
        s = df[col].dropna()
        if pd.api.types.is_numeric_dtype(s):
            return {
                "type":   "summary",
                "column": col,
                "mean":   round(float(s.mean()), 4),
                "median": round(float(s.median()), 4),
                "std":    round(float(s.std()), 4),
                "min":    round(float(s.min()), 4),
                "max":    round(float(s.max()), 4),
                "chart_suggestion": "histogram",
            }
        else:
            counts = s.value_counts().head(10)
            return {
                "type":    "summary",
                "column":  col,
                "unique":  int(s.nunique()),
                "top_val": str(s.mode().iloc[0]),
                "data":    counts.to_dict(),
                "chart_suggestion": "bar",
            }

    # Full dataset summary
    return {
        "type":  "summary",
        "rows":  len(df),
        "cols":  len(df.columns),
        "nulls": int(df.isnull().sum().sum()),
        "chart_suggestion": None,
    }


def _value_counts(df: pd.DataFrame, action: dict) -> dict:
    col = action.get("column")

    if col not in df.columns:
        return {"type": "error", "message": f"Column '{col}' not found"}

    counts = df[col].value_counts().head(10).reset_index()
    counts.columns = [col, "count"]

    return {
        "type":   "value_counts",
        "column": col,
        "data":   counts.to_dict(orient="records"),
        "x_col":  col,
        "y_col":  "count",
        "chart_suggestion": "bar",
    }


def _date_range(df: pd.DataFrame, action: dict) -> dict:
    col = action.get("column")

    if col not in df.columns:
        return {"type": "error", "message": f"Column '{col}' not found"}

    s = pd.to_datetime(df[col], errors="coerce").dropna()
    return {
        "type":       "date_range",
        "column":     col,
        "min":        str(s.min()),
        "max":        str(s.max()),
        "range_days": int((s.max() - s.min()).days),
        "chart_suggestion": "line",
    }


def _corr_strength(r: float) -> str:
    abs_r = abs(r)
    if abs_r >= 0.7:
        return "strong"
    elif abs_r >= 0.4:
        return "moderate"
    elif abs_r >= 0.2:
        return "weak"
    return "negligible"


def parse_action_from_question(question: str, columns: list) -> dict:
    """
    Simple rule-based action parser.
    On Day 9 Gemini will override this for complex questions.
    Used as fallback when Gemini structured response fails.
    """
    q = question.lower()

    # Top N pattern
    if 'top' in q:
        for col in columns:
            if col.lower() in q:
                n = 10
                for word in q.split():
                    if word.isdigit():
                        n = int(word)
                        break
                return {"type": "top_n", "column": col, "n": n}

    # Correlation pattern
    if any(k in q for k in ['correlat', 'relationship']):
        numeric_mentioned = [c for c in columns if c.lower() in q]
        if len(numeric_mentioned) >= 2:
            return {"type": "correlation",
                    "col1": numeric_mentioned[0],
                    "col2": numeric_mentioned[1]}
        return {"type": "correlation"}

    # Group by pattern
    if any(k in q for k in ['by', 'per', 'group', 'average', 'mean']):
        for col in columns:
            if col.lower() in q:
                for agg_col in columns:
                    if agg_col != col and agg_col.lower() in q:
                        return {"type": "group_by",
                                "column": col,
                                "agg_col": agg_col,
                                "agg": "mean"}

    # Value counts / distribution
    if any(k in q for k in ['distribution', 'count', 'how many', 'breakdown']):
        for col in columns:
            if col.lower() in q:
                return {"type": "value_counts", "column": col}

    # Summary fallback
    for col in columns:
        if col.lower() in q:
            return {"type": "summary", "column": col}

    return {"type": "summary"}