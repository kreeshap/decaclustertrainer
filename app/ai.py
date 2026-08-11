"""
ai.py — Thin wrappers around the Groq and Gemini SDKs.

Groq  : uses the official `groq` SDK
Gemini: uses the new `google-genai` SDK (google.genai)
"""

import json
import re

from .config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY

# ── Lazy clients ───────────────────────────────────────────────────────────────
_groq_client = None
_gemini_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


# ── Groq ───────────────────────────────────────────────────────────────────────


def call_groq(
    messages: list,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.7,
    response_json: bool = True,
    max_tokens: int = 2048,
) -> tuple:
    """Call Groq via the official SDK. Returns (data_or_text, error)."""
    if not GROQ_API_KEY:
        return None, "GROQ_API_KEY is not configured."
    try:
        kwargs = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_json:
            kwargs["response_format"] = {"type": "json_object"}

        resp = _get_groq().chat.completions.create(**kwargs)
        content = resp.choices[0].message.content.strip()
        if response_json:
            return json.loads(content), None
        return content, None
    except Exception as exc:
        msg = str(exc)
        # Pull out the human-readable message from Groq's error JSON if present
        m = re.search(r'"message"\s*:\s*"([^"]+)"', msg)
        return None, m.group(1) if m else f"Groq: {msg}"


# ── Gemini (JSON) ──────────────────────────────────────────────────────────────


def call_gemini_json(
    prompt: str,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    model: str = GEMINI_MODEL,
) -> tuple:
    """Call Gemini and return a parsed JSON dict. Returns (data, error)."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY is not configured."
    try:
        from google import genai
        from google.genai import types

        resp = _get_gemini().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        )
        text = resp.text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip()), None
    except Exception as exc:
        return None, f"Gemini: {exc}"


# ── Gemini (text) ──────────────────────────────────────────────────────────────


def call_gemini(
    prompt: str,
    model: str = GEMINI_MODEL,
) -> tuple:
    """Call Gemini and return raw text (used for grading). Returns (text, error)."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY is not configured."
    try:
        from google import genai
        from google.genai import types

        resp = _get_gemini().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
        return resp.text, None
    except Exception as exc:
        return None, f"Gemini: {exc}"
