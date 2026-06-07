import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import (
    SUPABASE_ANON_KEY,
    SUPABASE_API_TIMEOUT,
    SUPABASE_AUTH_URL,
    SUPABASE_REST_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)


def ensure_supabase_config():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY."
        )


def supabase_request(
    path: str,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return 500, {
            "detail": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.",
        }

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        f"{SUPABASE_AUTH_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=SUPABASE_API_TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        if body and "msg" not in parsed:
            parsed["msg"] = body
        return error.code, parsed
    except URLError as error:
        return 502, {"detail": f"Supabase request failed: {error.reason}"}
    except Exception as error:
        return 502, {"detail": f"Supabase request failed: {error}"}


def supabase_admin_request(path: str, method: str = "GET", payload: dict | None = None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return 500, {
            "detail": "Supabase admin is not configured. Set SUPABASE_SERVICE_ROLE_KEY.",
        }

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        f"{SUPABASE_AUTH_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=SUPABASE_API_TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        if body and "msg" not in parsed:
            parsed["msg"] = body
        return error.code, parsed
    except URLError as error:
        return 502, {"detail": f"Supabase admin request failed: {error.reason}"}
    except Exception as error:
        return 502, {"detail": f"Supabase admin request failed: {error}"}


def supabase_rest_request(
    path: str,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
    params: dict | None = None,
    prefer: str = "return=representation",
):
    """Call Supabase PostgREST (REST/v1) data API."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return 500, {"detail": "Supabase is not configured."}

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": prefer,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{SUPABASE_REST_URL}{path}"
    if params:
        # Use safe='' so nothing is percent-encoded — PostgREST filter syntax
        # uses characters like =, ., * that must be passed verbatim.
        url += "?" + "&".join(
            f"{k}={quote(str(v), safe='')}" for k, v in params.items()
        )

    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=SUPABASE_API_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        return e.code, parsed
    except URLError as e:
        return 502, {"detail": f"Supabase REST request failed: {e.reason}"}
    except Exception as e:
        return 502, {"detail": f"Supabase REST request failed: {e}"}
