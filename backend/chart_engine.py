import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json

# ── Dark theme constants (match your CSS vars) ────────────────
DARK = {
    'bg':       '#0f1117',
    'surface':  '#161b27',
    'surface2': '#1e2538',
    'border':   '#2a3147',
    'text':     '#e8eaf0',
    'text2':    '#8892a4',
    'text3':    '#5a6378',
    'accent':   '#7c6ef5',
    'teal':     '#2dd4a0',
    'amber':    '#f5a623',
    'red':      '#f56565',
    'blue':     '#60a5fa',
    'colors':   ['#7c6ef5','#2dd4a0','#f5a623','#f56565','#60a5fa',
                 '#a78bfa','#34d399','#fbbf24','#f87171','#93c5fd'],
}

BASE_LAYOUT = dict(
    paper_bgcolor = DARK['surface'],
    plot_bgcolor  = DARK['surface'],
    font          = dict(color=DARK['text2'], family='Inter, sans-serif', size=11),
    margin        = dict(t=32, r=16, b=48, l=48),
    xaxis         = dict(gridcolor=DARK['border'], linecolor=DARK['border'],
                         tickfont=dict(color=DARK['text3'])),
    yaxis         = dict(gridcolor=DARK['border'], linecolor=DARK['border'],
                         tickfont=dict(color=DARK['text3'])),
    legend        = dict(bgcolor='rgba(0,0,0,0)', font=dict(color=DARK['text2'])),
    hoverlabel    = dict(bgcolor=DARK['surface2'], font_color=DARK['text'],
                         bordercolor=DARK['border']),
)


def _apply_base(fig) -> go.Figure:
    fig.update_layout(**BASE_LAYOUT)
    return fig


def bar_chart(df: pd.DataFrame, x_col: str, y_col: str,
              title: str = '') -> str:
    """Categorical x, numeric y → vertical bar chart."""
    fig = go.Figure(go.Bar(
        x     = df[x_col].astype(str),
        y     = df[y_col],
        marker_color       = DARK['accent'],
        marker_line_color  = DARK['border'],
        marker_line_width  = 0.5,
        hovertemplate      = f'<b>%{{x}}</b><br>{y_col}: %{{y:.4f}}<extra></extra>',
    ))
    fig.update_layout(title=dict(text=title or f'{y_col} by {x_col}',
                                  font=dict(color=DARK['text'], size=12)))
    return _apply_base(fig).to_json()


def line_chart(df: pd.DataFrame, x_col: str, y_col: str,
               title: str = '') -> str:
    """Datetime/ordered x, numeric y → line chart."""
    df_sorted = df.sort_values(x_col)
    fig = go.Figure(go.Scatter(
        x    = df_sorted[x_col],
        y    = df_sorted[y_col],
        mode = 'lines+markers',
        line = dict(color=DARK['teal'], width=2),
        marker = dict(color=DARK['teal'], size=4),
        hovertemplate = f'<b>%{{x}}</b><br>{y_col}: %{{y:.4f}}<extra></extra>',
    ))
    fig.update_layout(title=dict(text=title or f'{y_col} over {x_col}',
                                  font=dict(color=DARK['text'], size=12)))
    return _apply_base(fig).to_json()


def histogram(df: pd.DataFrame, col: str, title: str = '') -> str:
    """Single numeric column → histogram."""
    fig = go.Figure(go.Histogram(
        x          = df[col].dropna(),
        nbinsx     = 30,
        marker_color      = DARK['accent'],
        marker_line_color = DARK['border'],
        marker_line_width = 0.5,
        hovertemplate     = 'Range: %{x}<br>Count: %{y}<extra></extra>',
    ))
    fig.update_layout(
        title    = dict(text=title or f'Distribution of {col}',
                        font=dict(color=DARK['text'], size=12)),
        bargap   = 0.05,
    )
    return _apply_base(fig).to_json()


def scatter_plot(df: pd.DataFrame, x_col: str, y_col: str,
                 color_col: str = None, title: str = '') -> str:
    """Two numeric columns → scatter plot."""
    if color_col and color_col in df.columns:
        fig = px.scatter(
            df, x=x_col, y=y_col, color=color_col,
            color_discrete_sequence=DARK['colors'],
        )
    else:
        fig = go.Figure(go.Scatter(
            x    = df[x_col],
            y    = df[y_col],
            mode = 'markers',
            marker = dict(color=DARK['accent'], size=5, opacity=0.7,
                          line=dict(color=DARK['border'], width=0.5)),
            hovertemplate = f'{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>',
        ))
    fig.update_layout(title=dict(text=title or f'{x_col} vs {y_col}',
                                  font=dict(color=DARK['text'], size=12)))
    return _apply_base(fig).to_json()


def heatmap_corr(df: pd.DataFrame, title: str = '') -> str:
    """Correlation matrix → annotated heatmap."""
    numeric = df.select_dtypes(include=[np.number])
    corr    = numeric.corr().round(4)

    fig = go.Figure(go.Heatmap(
        z          = corr.values,
        x          = list(corr.columns),
        y          = list(corr.index),
        colorscale = [
            [0.0,  DARK['red']],
            [0.5,  DARK['surface2']],
            [1.0,  DARK['teal']],
        ],
        zmid       = 0,
        text       = corr.round(2).astype(str).values,
        texttemplate = '%{text}',
        hovertemplate = '%{y} ↔ %{x}: %{z:.4f}<extra></extra>',
        showscale  = True,
        colorbar   = dict(
            tickfont   = dict(color=DARK['text3']),
            outlinecolor = DARK['border'],
        ),
    ))
    fig.update_layout(
        title  = dict(text=title or 'Correlation Matrix',
                      font=dict(color=DARK['text'], size=12)),
        xaxis  = dict(tickfont=dict(color=DARK['text3']), side='bottom'),
        yaxis  = dict(tickfont=dict(color=DARK['text3'])),
    )
    return _apply_base(fig).to_json()


def value_counts_chart(df: pd.DataFrame, col: str,
                        title: str = '') -> str:
    """Categorical column value counts → horizontal bar."""
    counts = df[col].value_counts().head(10).reset_index()
    counts.columns = [col, 'count']

    fig = go.Figure(go.Bar(
        x           = counts['count'],
        y           = counts[col].astype(str),
        orientation = 'h',
        marker_color      = DARK['teal'],
        marker_line_color = DARK['border'],
        marker_line_width = 0.5,
        hovertemplate = f'<b>%{{y}}</b><br>Count: %{{x}}<extra></extra>',
    ))
    fig.update_layout(
        title  = dict(text=title or f'{col} distribution',
                      font=dict(color=DARK['text'], size=12)),
        yaxis  = dict(autorange='reversed',
                      tickfont=dict(color=DARK['text3'])),
        xaxis  = dict(gridcolor=DARK['border'],
                      tickfont=dict(color=DARK['text3'])),
        margin = dict(t=32, r=16, b=32, l=100),
    )
    return _apply_base(fig).to_json()


# ── Auto-chart selector ───────────────────────────────────────
# YOUR decision tree — not a prompt to the LLM.
# Maps data types + query result type → best chart.

def auto_chart(df: pd.DataFrame, query_result: dict) -> tuple[str, str] | tuple[None, None]:
    """
    Decide which chart to render based on the query result type
    and the column data types.

    Returns: (chart_type_label, plotly_json) or (None, None)

    Decision tree:
      group_by result         → bar chart (category × numeric)
      value_counts result     → horizontal bar
      correlation (single)   → scatter plot
      correlation (matrix)   → heatmap
      top_n result            → bar chart
      summary (numeric col)  → histogram
      filter_by               → no chart (scalar result)
      error                   → no chart
    """
    rtype = query_result.get('type')

    if rtype == 'error' or rtype is None:
        return None, None

    # ── group_by → bar chart ──────────────────────────────────
    if rtype == 'group_by':
        data   = query_result.get('data', [])
        x_col  = query_result.get('x_col')
        y_col  = query_result.get('y_col')
        if not data or not x_col or not y_col:
            return None, None
        chart_df = pd.DataFrame(data)
        return 'bar (group_by)', bar_chart(chart_df, x_col, y_col)

    # ── value_counts → horizontal bar ────────────────────────
    elif rtype == 'value_counts':
        data  = query_result.get('data', [])
        x_col = query_result.get('x_col')
        y_col = query_result.get('y_col')
        if not data or not x_col:
            return None, None
        chart_df = pd.DataFrame(data)
        return 'bar (value_counts)', value_counts_chart(chart_df, x_col)

    # ── correlation single pair → scatter ─────────────────────
    elif rtype == 'correlation':
        col1 = query_result.get('col1')
        col2 = query_result.get('col2')
        if col1 and col2 and col1 in df.columns and col2 in df.columns:
            return 'scatter (correlation)', scatter_plot(df, col1, col2)
        return None, None

    # ── correlation matrix → heatmap ──────────────────────────
    elif rtype == 'correlation_matrix':
        return 'heatmap (correlation)', heatmap_corr(df)

    # ── top_n → bar chart ─────────────────────────────────────
    elif rtype == 'top_n':
        data  = query_result.get('data', [])
        col   = query_result.get('column')
        if not data or not col:
            return None, None
        chart_df = pd.DataFrame(data)
        if 'index' in chart_df.columns and col in chart_df.columns:
            chart_df['label'] = chart_df['index'].astype(str)
            fig = go.Figure(go.Bar(
                x     = chart_df['label'],
                y     = chart_df[col],
                marker_color      = DARK['amber'],
                marker_line_color = DARK['border'],
                marker_line_width = 0.5,
            ))
            fig.update_layout(
                title  = dict(text=f'Top {query_result.get("n")} by {col}',
                              font=dict(color=DARK['text'], size=12)),
            )
            return f'bar (top_{query_result.get("n")})', _apply_base(fig).to_json()
        return None, None

    # ── summary numeric col → histogram ───────────────────────
    elif rtype == 'summary':
        col = query_result.get('column')
        if col and col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            return 'histogram', histogram(df, col)
        return None, None

    # ── everything else → no chart ────────────────────────────
    return None, None