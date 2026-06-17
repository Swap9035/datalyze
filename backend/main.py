from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import tempfile

from backend import profiler, session_store , cleaner , outlier_detector , predictor

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