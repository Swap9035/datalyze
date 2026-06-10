from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="Datalyze API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Datalyze API", "version": "1.0.0"}


@app.get("/", response_class=FileResponse)
def serve_frontend():
    return os.path.join(frontend_path, "index.html")