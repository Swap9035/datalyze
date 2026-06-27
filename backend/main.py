from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import tempfile

from backend import profiler, session_store , cleaner , outlier_detector , predictor, llm, query_engine, chart_engine, trend_analyzer, report_generator
from dotenv import load_dotenv
load_dotenv()   # loads .env locally; on Render uses dashboard env vars

app = FastAPI(title="Datalyze API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(frontend_path, "static")),
    name="static"
)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
MAX_FILE_SIZE_MB = 50


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Datalyze API", "version": "1.0.0"}


@app.get("/", response_class=FileResponse)
def serve_frontend():
    return os.path.join(frontend_path, "index.html")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Accepts CSV, Excel, or JSON. Parses with pandas, profiles the
    dataset, stores it in the session store, and returns a summary.
    """
    # 1. Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 2. Save to a temp file (pandas needs a path or file-like object)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    # 3. Check file size
    size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        os.remove(tmp_path)
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Max is {MAX_FILE_SIZE_MB} MB."
        )

    # 4. Parse with pandas
    try:
        df = profiler.load_dataframe(tmp_path, file.filename)
    except Exception as e:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded file contains no data.")

    # 5. Profile + store session
    profile = profiler.profile_dataframe(df)
    insights = profiler.quick_insights(df, profile)
    session_id = session_store.create_session(df, file.filename)

    return {
        "session_id": session_id,
        "filename": file.filename,
        "profile": profile,
        "insights": insights,
    }


@app.get("/profile/{session_id}")
def get_profile(session_id: str):
    """Re-fetch the profile for an existing session."""
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Please re-upload your file.")

    df = session["df"]
    profile = profiler.profile_dataframe(df)
    insights = profiler.quick_insights(df, profile)

    return {
        "session_id": session_id,
        "filename": session["filename"],
        "profile": profile,
        "insights": insights,
    }

@app.post("/clean/{session_id}")
def clean_session_data(session_id: str):
    """
    Run the cleaning pipeline on the session's DataFrame,
    store the cleaned version back in the session, and
    return a before/after report.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Please re-upload your file.")

    df_before = session["df"]
    profile_before = profiler.profile_dataframe(df_before)

    df_after, report = cleaner.clean_dataframe(df_before)

    # Persist the cleaned DataFrame for downstream steps (Day 5+)
    session_store.update_session_df(session_id, df_after)

    profile_after = profiler.profile_dataframe(df_after)
    summary_lines = cleaner.cleaning_summary_text(report)
    session["cleaning_report"] = report

    return {
        "session_id": session_id,
        "report": report,
        "summary": summary_lines,
        "profile_before": profile_before,
        "profile_after": profile_after,
    }

@app.get("/stats/{session_id}")
def get_column_stats(session_id: str):
    """
    Return deep per-column statistics for an existing session.
    All computed by profiler.py — LLM will narrate these on Day 9.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your file."
        )

    df      = session["df"]
    profile = profiler.profile_dataframe(df)
    stats   = profiler.compute_column_stats(df)
    context = profiler.build_context_for_llm(df, profile, stats)

    # Cache context string in session for fast LLM access on Day 9
    session_store.get_session(session_id)["llm_context"] = context
    session_store.get_session(session_id)["col_stats"]   = stats

    return {
        "session_id": session_id,
        "profile":    profile,
        "col_stats":  stats,
        "llm_context": context,
    }

@app.get("/outliers/{session_id}")
def get_outliers(session_id: str):
    """
    Run IQR + z-score outlier detection on the cleaned DataFrame.
    Returns per-column results, comparison, and plain-English summary.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your file."
        )

    df = session["df"]

    iqr_results    = outlier_detector.detect_outliers_iqr(df)
    zscore_results = outlier_detector.detect_outliers_zscore(df)
    comparison     = outlier_detector.compare_methods(iqr_results, zscore_results)
    summary        = outlier_detector.outlier_summary_text(iqr_results, zscore_results)

    # Cache in session for LLM context on Day 9
    session["outlier_summary"] = summary
    session["iqr_results"]      = iqr_results
    session["zscore_results"]   = zscore_results


    return {
        "session_id":    session_id,
        "iqr_results":   iqr_results,
        "zscore_results": zscore_results,
        "comparison":    comparison,
        "summary":       summary,
    }

@app.post("/train/{session_id}")
def train_model(session_id: str):
    """
    Train a logistic regression model on the session's cleaned DataFrame.
    Stores the trained model bundle in the session for /predict calls.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your file."
        )

    df = session["df"]

    try:
        model_bundle = predictor.train_model(df)
    except ValueError as e:
    # Return 200 with skipped=True instead of crashing
    # so the frontend continues loading other features
        return {
            "session_id": session_id,
            "skipped": True,
            "reason": str(e),
            "metrics": None,
            "feature_importance": [],
            "confusion_matrix": None,
            "summary": [str(e)],
            "train_size": 0,
            "test_size": 0,
        }

    # Store model bundle — excludes sklearn objects for JSON response
    session["model_bundle"] = model_bundle
    summary = predictor.model_summary_text(model_bundle)

    return {
        "session_id":         session_id,
        "target":             model_bundle["target"],
        "train_size":         model_bundle["train_size"],
        "test_size":          model_bundle["test_size"],
        "metrics":            model_bundle["metrics"],
        "confusion_matrix":   model_bundle["confusion_matrix"],
        "feature_importance": model_bundle["feature_importance"],
        "summary":            summary,
    }


@app.post("/predict/{session_id}")
def predict(session_id: str, input_data: dict):
    """
    Predict survival for a single input row using the trained model.
    Requires /train to have been called first.
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your file."
        )

    model_bundle = session.get("model_bundle")
    if model_bundle is None:
        raise HTTPException(
            status_code=400,
            detail="Model not trained yet. Call POST /train/{session_id} first."
        )

    try:
        result = predictor.predict_single(model_bundle, input_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result

@app.post("/chat/{session_id}")
def chat(session_id: str, body: dict):
    """
    Main chat endpoint — Day 10 upgrade.
    Flow:
      1. Load session context
      2. Classify question type
      3. Ask Gemini to parse question → structured JSON action
      4. Execute action on real DataFrame (your pandas code)
      5. Build prompt with pre-computed context + query result
      6. Ask Gemini to narrate the result
      7. Return structured response: answer + chart hint + method
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please re-upload your file."
        )

    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    df           = session["df"]
    llm_context  = session.get("llm_context", "")
    col_stats    = session.get("col_stats", {})
    outlier_sum  = session.get("outlier_summary", [])
    model_bundle = session.get("model_bundle")

    model_sum = []
    if model_bundle:
        model_sum = predictor.model_summary_text(model_bundle)

    columns = list(df.columns)

    # ── 1. Classify question ──────────────────────────────────
    question_type = llm.classify_question(question)

    # ── 2. Parse question → structured action ─────────────────
    # Gemini decides what to compute.
    # Your query_engine.py does the actual computing.
    if question_type in ('stats', 'chart', 'general'):
        action = llm.parse_query_action(question, columns, col_stats)
    else:
        # For outlier/model questions use rule-based parser
        from backend.query_engine import parse_action_from_question
        action = parse_action_from_question(question, columns)

    # ── 3. Execute action on real DataFrame ───────────────────
    query_result  = query_engine.run_query(df, action)
    method_label  = action.get("type", "query")
    chart_hint    = query_result.get("chart_suggestion")

    # ── 4. Build rich context for narration ───────────────────
    context = llm_context
    if query_result and query_result.get("type") != "error":
        # Summarize result for LLM (keep token usage low)
        result_summary = _summarize_query_result(query_result)
        context += f"\n\nQuery executed: {action}\nResult: {result_summary}"

    prompt = llm.build_prompt(
        llm_context     = context,
        question        = question,
        outlier_summary = outlier_sum,
        model_summary   = model_sum,
    )

    # ── 5. Gemini narrates ────────────────────────────────────
    answer = llm.ask_gemini(prompt)

    # ── 6. Auto-select + generate chart ──────────────────────
    # YOUR decision tree picks the chart — not the LLM.
    chart_label, chart_json = chart_engine.auto_chart(df, query_result)

    # ── 7. Build insight card for grouped/model results ───────
    insight = None
    if chart_json and query_result.get('type') in ('group_by', 'value_counts'):
        insight = _build_insight_from_result(query_result, answer)

    return {
        "answer":        answer,
        "question_type": question_type,
        "chart":         chart_json,
        "chart_type":    chart_label,
        "insight":       insight,
        "method":        method_label,
        "query_result":  query_result,
        "action":        action,
    }


def _summarize_query_result(result: dict) -> str:
    """
    Convert a query result into a compact text summary for the LLM.
    Keeps token usage low — LLM gets the key numbers, not raw data.
    """
    rtype = result.get("type")

    if rtype == "group_by":
        data   = result.get("data", [])
        x_col  = result.get("x_col")
        y_col  = result.get("y_col")
        lines  = [f"{row[x_col]}: {round(row[y_col], 4)}" for row in data[:10]]
        return f"Group by result ({x_col} → {y_col}): " + ", ".join(lines)

    elif rtype == "top_n":
        data  = result.get("data", [])
        col   = result.get("column")
        lines = [f"row {row.get('index', i)}: {row.get(col)}"
                 for i, row in enumerate(data[:5])]
        return f"Top {result.get('n')} by {col}: " + ", ".join(lines)

    elif rtype == "filter_by":
        return (
            f"Filter {result.get('column')} = '{result.get('value')}': "
            f"{result.get('matched_rows')} rows matched "
            f"({result.get('pct')}% of dataset)"
        )

    elif rtype == "correlation":
        return (
            f"Correlation between {result.get('col1')} and {result.get('col2')}: "
            f"r = {result.get('value')} ({result.get('strength')} relationship)"
        )

    elif rtype == "correlation_matrix":
        cols = result.get("columns", [])
        matrix = result.get("matrix", {})
        # Show top correlations only
        pairs = []
        for i, c1 in enumerate(cols):
            for c2 in cols[i+1:]:
                val = matrix.get(c1, {}).get(c2, 0)
                pairs.append((c1, c2, round(val, 4)))
        pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        top = [f"{p[0]}↔{p[1]}: {p[2]}" for p in pairs[:5]]
        return "Top correlations: " + ", ".join(top)

    elif rtype == "summary":
        col = result.get("column")
        if col and "mean" in result:
            return (
                f"{col} stats: mean={result.get('mean')}, "
                f"median={result.get('median')}, "
                f"std={result.get('std')}, "
                f"min={result.get('min')}, max={result.get('max')}"
            )
        elif col and "unique" in result:
            return (
                f"{col}: {result.get('unique')} unique values, "
                f"most common: '{result.get('top_val')}'"
            )
        return f"Dataset: {result.get('rows')} rows, {result.get('cols')} cols"

    elif rtype == "value_counts":
        data = result.get("data", [])
        col  = result.get("column")
        lines = [f"{row[col]}: {row['count']}" for row in data[:5]]
        return f"Value counts for {col}: " + ", ".join(lines)

    elif rtype == "date_range":
        return (
            f"{result.get('column')} ranges from {result.get('min')} "
            f"to {result.get('max')} ({result.get('range_days')} days)"
        )

    return str(result)[:200]


def _parse_insight(raw: str) -> dict | None:
    """Parse Gemini's 3-line insight format into a dict."""
    try:
        lines  = raw.strip().split('\n')
        result = {}
        for line in lines:
            if line.startswith('WHAT:'):
                result['what_happened']  = line[5:].strip()
            elif line.startswith('WHY:'):
                result['why_it_matters'] = line[4:].strip()
            elif line.startswith('NEXT:'):
                result['next_question']  = line[5:].strip()
        if len(result) == 3:
            return result
        return None
    except Exception:
        return None
    
def _build_insight_from_result(query_result: dict, answer: str) -> dict | None:
    """
    Build a structured insight card from query result + Gemini answer.
    No extra API call — derived from the data we already have.
    """
    rtype = query_result.get('type')

    if rtype == 'group_by':
        data   = query_result.get('data', [])
        x_col  = query_result.get('x_col', '')
        y_col  = query_result.get('y_col', '')

        if not data:
            return None

        values    = [row.get(y_col, 0) for row in data]
        max_row   = data[values.index(max(values))]
        min_row   = data[values.index(min(values))]
        max_label = str(max_row.get(x_col, ''))
        min_label = str(min_row.get(x_col, ''))
        max_val   = round(max(values), 4)
        min_val   = round(min(values), 4)
        spread    = round(max_val - min_val, 4)

        return {
            "what_happened":  f"{max_label} has the highest value ({max_val}), "
                              f"{min_label} the lowest ({min_val}).",
            "why_it_matters": f"A spread of {spread} between groups suggests "
                              f"{x_col} is a meaningful differentiator.",
            "next_question":  f"Try: 'show {y_col} by another categorical column'",
            "trend":          None,
        }

    elif rtype == 'value_counts':
        data  = query_result.get('data', [])
        x_col = query_result.get('x_col', '')

        if not data:
            return None

        top   = data[0]
        total = sum(row.get('count', 0) for row in data)
        top_pct = round(100 * top.get('count', 0) / total, 1) if total else 0

        return {
            "what_happened":  f"'{top.get(x_col)}' is the most common value "
                              f"({top.get('count')} occurrences, {top_pct}%).",
            "why_it_matters": f"{x_col} has {len(data)} distinct values — "
                              f"{'low' if len(data) <= 5 else 'high'} cardinality.",
            "next_question":  f"Try: 'show survival rate by {x_col}'",
            "trend":          None,
        }

    return None

@app.get("/trends/{session_id}")
def get_trends(session_id: str):
    """Detect trends in numeric/datetime columns."""
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404,
                            detail="Session not found.")

    df      = session["df"]
    results = trend_analyzer.detect_trends(df)
    summary = trend_analyzer.trend_summary_text(results)

    session["trend_results"] = results

    return {
        "session_id":    session_id,
        "trend_results": results,
        "summary":       summary,
    }


@app.get("/export/report/{session_id}")
def export_report(session_id: str):
    """Export full Markdown analysis report."""
    from fastapi.responses import Response

    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404,
                            detail="Session not found.")

    df       = session["df"]
    filename = session.get("filename", "dataset")
    profile  = profiler.profile_dataframe(df)
    stats    = session.get("col_stats") or profiler.compute_column_stats(df)
    insights = profiler.quick_insights(df, profile)

    cleaning = session.get("cleaning_report", {})
    iqr      = session.get("iqr_results", {})
    zscore   = session.get("zscore_results", {})
    trends   = session.get("trend_results")

    model_metrics = None
    feature_imp   = None
    bundle        = session.get("model_bundle")
    if bundle:
        model_metrics = bundle["metrics"]
        feature_imp   = bundle["feature_importance"]

    md = report_generator.generate_markdown_report(
        filename        = filename,
        profile         = profile,
        cleaning_report = cleaning,
        col_stats       = stats,
        outlier_iqr     = iqr,
        outlier_zscore  = zscore,
        model_metrics   = model_metrics,
        feature_importance = feature_imp,
        trend_results   = trends,
        insights        = insights,
    )

    return Response(
        content     = md,
        media_type  = "text/markdown",
        headers     = {
            "Content-Disposition":
                f'attachment; filename="datalyze_report_{filename}.md"'
        },
    )


@app.get("/export/csv/{session_id}")
def export_csv(session_id: str):
    """Export column stats summary as CSV."""
    from fastapi.responses import Response

    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404,
                            detail="Session not found.")

    df      = session["df"]
    profile = profiler.profile_dataframe(df)
    stats   = session.get("col_stats") or profiler.compute_column_stats(df)
    iqr     = session.get("iqr_results", {})

    csv_content = report_generator.generate_csv_summary(profile, stats, iqr)

    return Response(
        content    = csv_content,
        media_type = "text/csv",
        headers    = {
            "Content-Disposition":
                'attachment; filename="datalyze_summary.csv"'
        },
    )