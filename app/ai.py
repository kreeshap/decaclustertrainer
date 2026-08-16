"""Thin provider adapters. Routing and retries live in ai_coordinator.py."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import (
    GEMINI_API_KEY,
    GEMINI_API_TIMEOUT,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_API_TIMEOUT,
    MISTRAL_API_KEY,
    MISTRAL_API_TIMEOUT,
    MISTRAL_MODEL,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_KEY,
    CLOUDFLARE_API_TIMEOUT,
    CLOUDFLARE_MODEL,
)

# ── Lazy clients ───────────────────────────────────────────────────────────────
_groq_client = None
_gemini_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        # Disable SDK retries here: learn-generation already falls back to
        # Gemini, and retries can outlive the web worker's request timeout.
        _groq_client = Groq(
            api_key=GROQ_API_KEY,
            timeout=GROQ_API_TIMEOUT,
            max_retries=0,
        )
    return _groq_client


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        from google.genai import types

        # google-genai expresses HttpOptions.timeout in milliseconds.
        _gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=int(GEMINI_API_TIMEOUT * 1000)),
        )
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
    retry_invalid_json: bool = False,
) -> tuple:
    """Call Gemini and return a parsed JSON dict. Returns (data, error)."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY is not configured."
    try:
        from google import genai
        from google.genai import types

        attempts = 2 if retry_invalid_json else 1
        last_error = None
        for attempt in range(attempts):
            contents = prompt
            if attempt:
                contents += (
                    "\n\nYour previous response was malformed or truncated. Regenerate the complete "
                    "object from scratch. Use short sentences, stay well below the output limit, "
                    "and return strict JSON only."
                )
            resp = _get_gemini().models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1 if attempt else temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )
            text = (resp.text or "").strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            try:
                return json.loads(text.strip()), None
            except json.JSONDecodeError as exc:
                last_error = exc
        return None, f"Gemini returned malformed JSON after {attempts} attempt(s): {last_error}"
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


def _openai_compatible_call(*, provider: str, url: str, api_key: str, model: str,
                            messages: list, timeout: float, temperature: float,
                            max_tokens: int, response_json: bool) -> tuple:
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_json:
        payload["response_format"] = {"type": "json_object"}
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    }, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"].strip()
        return (json.loads(content), None) if response_json else (content, None)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        return None, f"{provider}: HTTP {exc.code}: {detail}"
    except (URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return None, f"{provider}: {exc}"


def call_mistral(messages: list, model: str = MISTRAL_MODEL, temperature: float = 0.2,
                 response_json: bool = True, max_tokens: int = 6000) -> tuple:
    if not MISTRAL_API_KEY:
        return None, "MISTRAL_API_KEY is not configured."
    return _openai_compatible_call(
        provider="Mistral", url="https://api.mistral.ai/v1/chat/completions",
        api_key=MISTRAL_API_KEY, model=model, messages=messages,
        timeout=MISTRAL_API_TIMEOUT, temperature=temperature,
        max_tokens=max_tokens, response_json=response_json,
    )


def call_cloudflare(messages: list, model: str = CLOUDFLARE_MODEL, temperature: float = 0.2,
                    response_json: bool = True, max_tokens: int = 6000) -> tuple:
    if not CLOUDFLARE_API_KEY:
        return None, "CLOUDFLARE_API_KEY is not configured."
    if not CLOUDFLARE_ACCOUNT_ID:
        return None, "CLOUDFLARE_ACCOUNT_ID is not configured."
    return _openai_compatible_call(
        provider="Cloudflare",
        url=f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions",
        api_key=CLOUDFLARE_API_KEY, model=model, messages=messages,
        timeout=CLOUDFLARE_API_TIMEOUT, temperature=temperature,
        max_tokens=max_tokens, response_json=response_json,
    )


def call_json_with_fallback(prompt: str, *, priority: str = "student", temperature: float = 0.2,
                            max_tokens: int = 2048) -> tuple:
    """Return structured output using controlled, health-aware provider failover."""
    from .ai_coordinator import coordinator
    messages = [{"role": "user", "content": prompt}]
    result, error, _ = coordinator.run([
        ("Groq", lambda: call_groq(messages, temperature=temperature, max_tokens=max_tokens)),
        ("Mistral", lambda: call_mistral(messages, temperature=temperature, max_tokens=max_tokens)),
        ("Cloudflare", lambda: call_cloudflare(messages, temperature=temperature, max_tokens=max_tokens)),
        ("Gemini", lambda: call_gemini_json(prompt, temperature=temperature, max_tokens=max_tokens, retry_invalid_json=True)),
    ], priority)
    return result, error
