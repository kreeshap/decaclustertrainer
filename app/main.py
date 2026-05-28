import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, make_response, render_template, request


BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(BASE_DIR / ".env")

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


def normalize_supabase_url(raw_url: str) -> str:
    """
    Accept either the project base URL or an accidentally pasted REST/API URL.
    Supabase auth endpoints need the project base URL, not /rest/v1.
    """
    url = (raw_url or "").strip().rstrip("/")
    for suffix in ("/rest/v1", "/auth/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


SUPABASE_URL = normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_AUTH_URL = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else ""
SUPABASE_API_TIMEOUT = float(os.environ.get("SUPABASE_API_TIMEOUT", "6"))
LOGIN_LIMIT_MAX_FAILURES = int(os.environ.get("LOGIN_LIMIT_MAX_FAILURES", "5"))
LOGIN_LIMIT_WINDOW_SECONDS = int(os.environ.get("LOGIN_LIMIT_WINDOW_SECONDS", "600"))
LOGIN_LIMIT_COOLDOWN_SECONDS = int(os.environ.get("LOGIN_LIMIT_COOLDOWN_SECONDS", "600"))
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME", "ct_refresh_token")
REFRESH_COOKIE_MAX_AGE = int(os.environ.get("REFRESH_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))
_LOGIN_FAILURES: dict[str, list[float]] = {}


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or request.remote_addr or "unknown"
    return request.remote_addr or "unknown"


def login_limit_key(email: str | None = None, ip: str | None = None) -> str:
    return f"{normalize_email(email)}|{ip or get_client_ip()}"


def prune_login_failures(entries: list[float], now: float) -> list[float]:
    cutoff = now - LOGIN_LIMIT_WINDOW_SECONDS
    return [ts for ts in entries if ts >= cutoff]


def login_limit_status(email: str | None = None, ip: str | None = None) -> tuple[bool, int]:
    key = login_limit_key(email, ip)
    now = time.time()
    entries = prune_login_failures(_LOGIN_FAILURES.get(key, []), now)
    _LOGIN_FAILURES[key] = entries

    if len(entries) < LOGIN_LIMIT_MAX_FAILURES:
        return False, 0

    retry_after = max(1, int(LOGIN_LIMIT_COOLDOWN_SECONDS - (now - entries[0])))
    if retry_after <= 0:
        _LOGIN_FAILURES[key] = []
        return False, 0

    return True, retry_after


def record_login_failure(email: str | None = None, ip: str | None = None) -> tuple[bool, int]:
    key = login_limit_key(email, ip)
    now = time.time()
    entries = prune_login_failures(_LOGIN_FAILURES.get(key, []), now)
    entries.append(now)
    _LOGIN_FAILURES[key] = entries

    if len(entries) < LOGIN_LIMIT_MAX_FAILURES:
        return False, 0

    return True, LOGIN_LIMIT_COOLDOWN_SECONDS


def clear_login_failures(email: str | None = None, ip: str | None = None) -> None:
    _LOGIN_FAILURES.pop(login_limit_key(email, ip), None)


def is_local_host(hostname: str | None) -> bool:
    hostname = (hostname or "").split(":", 1)[0].lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def cookie_secure_flag() -> bool:
    return not is_local_host(request.host)


def set_refresh_cookie(response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite="Lax",
        path="/",
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path="/",
        samesite="Lax",
    )


def display_name_from_email(email: str) -> str:
    email = normalize_email(email)
    return email.split("@", 1)[0] if "@" in email else email or "User"


def ensure_supabase_config():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY."
        )


def supabase_request(path: str, method: str = "GET", token: str | None = None, payload: dict | None = None):
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


def find_supabase_user_by_email(email: str):
    target_email = normalize_email(email)
    status, data = supabase_admin_request("/admin/users")
    if status != 200:
        return None, data

    users = data.get("users") or []
    for user in users:
        if normalize_email(user.get("email")) == target_email:
            return user, None

    return None, None


def serialize_user(user: dict) -> dict:
    user_metadata = user.get("user_metadata") or {}
    display_name = (
        user.get("display_name")
        or user_metadata.get("display_name")
        or user_metadata.get("full_name")
        or user_metadata.get("name")
        or display_name_from_email(user.get("email", ""))
    )

    return {
        "id": user.get("id"),
        "email": user.get("email") or "",
        "display_name": display_name,
    }


def auth_response(data: dict, status_code: int = 200):
    session = data.get("session") or {}
    user = data.get("user") or {}
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")

    if not access_token:
        response = make_response(jsonify({
            "user": serialize_user(user),
            "detail": "Check your email to confirm the account before signing in.",
        }), 202)
        if refresh_token:
            set_refresh_cookie(response, refresh_token)
        return response

    response = make_response(jsonify({
        "access_token": access_token,
        "user": serialize_user(user),
    }), status_code)
    if refresh_token:
        set_refresh_cookie(response, refresh_token)
    return response


def get_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.removeprefix("Bearer ").strip() or None


def get_current_user():
    token = get_bearer_token()
    if not token:
        return None

    status, data = supabase_request("/user", token=token)
    if status != 200 or not isinstance(data, dict):
        return None

    return data


@app.get("/")
def home():
    return render_template("signon.html")


@app.get("/app/index.html")
def app_index():
    return render_template("signon.html")


@app.get("/reset-password")
def reset_password():
    return render_template("signon.html")


@app.get("/app/dashboard.html")
def dashboard():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Dashboard</title>
        <script defer src="/static/js/common.js"></script>
        <style>
          :root { color-scheme: dark; }
          body {
            margin: 0;
            min-height: 100vh;
            background: #081415;
            color: #eef7f7;
            font-family: Barlow, Arial, sans-serif;
          }
          .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 28px;
            border-bottom: 1px solid rgba(255,255,255,.05);
            background: rgba(9, 24, 24, .75);
          }
          .app-brand {
            cursor: pointer;
            font-family: "Barlow Condensed", Arial, sans-serif;
            font-size: 1.4rem;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
          }
          .topbar-actions {
            display: flex;
            align-items: center;
            gap: 12px;
          }
          .pill {
            padding: 10px 14px;
            border: 1px solid rgba(255,255,255,.08);
            background: rgba(255,255,255,.03);
            color: inherit;
            text-decoration: none;
            cursor: pointer;
          }
          main {
            padding: 28px;
          }
        </style>
      </head>
      <body>
        <header class="topbar">
          <div class="app-brand">Cluster Trainer</div>
          <div class="topbar-actions">
            <div id="topbar-name">User</div>
            <button class="pill" id="btn-settings" type="button">Settings</button>
            <button class="pill" id="btn-logout" type="button">Log out</button>
          </div>
        </header>
        <main>
          <h1>Dashboard</h1>
          <p>You are signed in.</p>
        </main>
        <script>
          requireAuth().then((user) => {
            if (user) {
              initTopbar(user);
            }
          });
        </script>
      </body>
    </html>
    """


@app.get("/app/settings.html")
def settings():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Settings</title>
        <script defer src="/static/js/common.js"></script>
      </head>
      <body style="margin:0;min-height:100vh;background:#081415;color:#eef7f7;font-family:Barlow,Arial,sans-serif;">
        <script>
          requireAuth().then((user) => {
            if (!user) return;
            document.body.innerHTML = '<main style="padding:28px;"><h1>Settings</h1><p>Placeholder page.</p></main>';
            initTopbar(user);
          });
        </script>
      </body>
    </html>
    """


@app.post("/auth/signin")
def signin():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    password = payload.get("password") or ""
    client_ip = get_client_ip()

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

    limited, retry_after = login_limit_status(email, client_ip)
    if limited:
        return jsonify({
            "detail": "Too many login attempts. Please wait before trying again.",
            "retry_after_seconds": retry_after,
        }), 429

    status, data = supabase_request(
        "/token?grant_type=password",
        method="POST",
        payload={"email": email, "password": password},
    )

    if status != 200:
        message = (
            data.get("msg")
            or data.get("error_description")
            or data.get("detail")
            or "Invalid email or password."
        )
        limited, retry_after = record_login_failure(email, client_ip)
        if limited:
            return jsonify({
                "detail": "Too many login attempts. Please wait before trying again.",
                "retry_after_seconds": retry_after,
            }), 429
        return jsonify({"detail": message}), 401

    clear_login_failures(email, client_ip)
    return auth_response(data)


@app.post("/auth/signup")
def signup():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or payload.get("name") or "").strip()

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters."}), 400

    status, data = supabase_request(
        "/signup",
        method="POST",
        payload={
            "email": email,
            "password": password,
            "data": {
                "display_name": display_name or display_name_from_email(email),
            },
        },
    )

    if status not in (200, 201):
        message = (
            data.get("msg")
            or data.get("error_description")
            or data.get("detail")
            or "Sign up failed."
        )
        return jsonify({"detail": message}), status

    return auth_response(data, status_code=201)


@app.get("/auth/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    return jsonify({"user": serialize_user(user)})


@app.post("/auth/session")
def session_sync():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""

    if not refresh_token:
        return jsonify({"detail": "Missing refresh token."}), 400

    response = make_response(jsonify({"message": "Session stored."}))
    set_refresh_cookie(response, refresh_token)
    return response


@app.post("/auth/refresh")
def refresh_session():
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME) or ""

    if not refresh_token:
        response = make_response(jsonify({"detail": "Missing refresh session."}), 401)
        clear_refresh_cookie(response)
        return response

    status, data = supabase_request(
        "/token?grant_type=refresh_token",
        method="POST",
        payload={"refresh_token": refresh_token},
    )

    if status != 200:
        message = (
            data.get("msg")
            or data.get("error_description")
            or data.get("detail")
            or "Unable to refresh session."
        )
        response = make_response(jsonify({"detail": message}), 401)
        clear_refresh_cookie(response)
        return response

    return auth_response(data)


@app.post("/auth/logout")
def logout():
    response = make_response(jsonify({"message": "Logged out."}), 200)
    clear_refresh_cookie(response)
    return response


@app.post("/auth/password-reset/request")
def password_reset_request():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))

    if not email:
        return jsonify({"detail": "Please enter your email address."}), 400

    existing_user, lookup_error = find_supabase_user_by_email(email)
    if lookup_error:
        message = (
            lookup_error.get("msg")
            or lookup_error.get("error_description")
            or lookup_error.get("detail")
            or "Unable to verify account."
        )
        return jsonify({"detail": message}), 502

    if not existing_user:
        return jsonify({"detail": "No account found for that email address."}), 404

    redirect_to = f"{request.host_url.rstrip('/')}/reset-password"
    status, data = supabase_request(
        "/recover",
        method="POST",
        payload={
            "email": email,
            "redirect_to": redirect_to,
        },
    )

    if status != 200:
        message = (
            data.get("msg")
            or data.get("error_description")
            or data.get("detail")
            or "Unable to send reset link."
        )
        return jsonify({"detail": message}), status

    return jsonify({"message": "Reset link sent. Check your email."})


@app.post("/auth/password-reset/complete")
def password_reset_complete():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Missing recovery session."}), 401

    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""

    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters."}), 400

    status, data = supabase_request(
        "/user",
        method="PUT",
        token=token,
        payload={"password": password},
    )

    if status not in (200, 201):
        message = (
            data.get("msg")
            or data.get("error_description")
            or data.get("detail")
            or "Unable to update password."
        )
        return jsonify({"detail": message}), status

    return jsonify({"message": "Password updated successfully."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
