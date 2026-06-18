import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_api_key  = os.getenv("GEMINI_API_KEY")
_client   = genai.Client(api_key=_api_key) if _api_key else None
MODEL = "gemini-flash-lite-latest"

SYSTEM_PROMPT = """You are Datalyze, a data analysis assistant.
You receive pre-computed statistics about a dataset and answer
user questions based ONLY on those statistics.

Rules:
- Be concise — 2-4 sentences max unless asked for detail
- Never make up numbers — only use stats provided to you
- When referencing numbers, be specific (e.g. "63.0% survival rate")
- If a question is unrelated to the data, politely redirect
- Never say "As an AI language model"
- Speak as a data analyst, not a chatbot
"""


def build_prompt(llm_context: str, question: str,
                 outlier_summary: list = None,
                 model_summary: list = None) -> str:
    parts = [
        "=== DATASET CONTEXT (pre-computed) ===",
        llm_context,
    ]
    if outlier_summary:
        parts.append("\n=== OUTLIER FINDINGS (pre-computed) ===")
        parts.extend(outlier_summary)
    if model_summary:
        parts.append("\n=== ML MODEL RESULTS (pre-computed) ===")
        parts.extend(model_summary)

    parts.append(f"\n=== USER QUESTION ===\n{question}")
    parts.append(
        "\nAnswer based only on the pre-computed context above. "
        "Be specific with numbers. Be concise."
    )
    return "\n".join(parts)


def classify_question(question: str) -> str:
    q = question.lower()
    chart_kw   = ['show','plot','chart','graph','visuali','bar','histogram','scatter','distribution']
    outlier_kw = ['outlier','anomal','extreme','unusual','spike']
    model_kw   = ['predict','model','accuracy','feature','importan','surviv','classif','f1','precision','recall']
    stat_kw    = ['mean','median','average','max','min','count','null','missing','duplicate','correlation','std']

    if any(k in q for k in chart_kw):   return 'chart'
    if any(k in q for k in outlier_kw): return 'outliers'
    if any(k in q for k in model_kw):   return 'model'
    if any(k in q for k in stat_kw):    return 'stats'
    return 'general'


def ask_gemini(prompt: str) -> str:
    if not _client:
        return "Gemini API key not configured. Add GEMINI_API_KEY to your .env file."

    time.sleep(1)

    try:
        response = _client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=300,
                temperature=0.3,
            ),
        )
        return response.text.strip()

    except Exception as e:
        err = str(e).lower()
        if '429' in err or 'quota' in err or 'exhausted' in err:
            return (
                "Gemini API daily quota reached. "
                "Please create a new API key at ai.google.dev "
                "or wait until tomorrow for the quota to reset."
            )
        if 'api_key' in err or 'invalid' in err:
            return "Invalid Gemini API key. Check your .env file."
        return f"Gemini error: {str(e)[:200]}"


def build_insight_card(what_happened, why_it_matters, next_question, trend=None):
    return {
        "what_happened":  what_happened,
        "why_it_matters": why_it_matters,
        "next_question":  next_question,
        "trend":          trend,
    }