import uuid
import pandas as pd

# In-memory session store.
# Structure: { session_id: {"df": DataFrame, "filename": str} }
_sessions: dict[str, dict] = {}


def create_session(df: pd.DataFrame, filename: str) -> str:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"df": df, "filename": filename}
    return session_id


def get_session(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def update_session_df(session_id: str, df: pd.DataFrame) -> None:
    if session_id in _sessions:
        _sessions[session_id]["df"] = df


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)