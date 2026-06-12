from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import tempfile

from backend import profiler, session_store , cleaner

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