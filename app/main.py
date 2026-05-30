import json
import os
import hashlib
import secrets
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
LOGIN_LIMIT_WINDOW_SECONDS = int(os.environ.get("LOGIN_LIMIT_WINDOW_SECONDS", "900"))
LOGIN_LIMIT_COOLDOWN_SECONDS = int(os.environ.get("LOGIN_LIMIT_COOLDOWN_SECONDS", "900"))
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME", "ct_refresh_token")
REMEMBER_COOKIE_NAME = os.environ.get("REMEMBER_COOKIE_NAME", "ct_remember_me")
REFRESH_COOKIE_MAX_AGE = int(os.environ.get("REFRESH_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))
_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCKS: dict[str, dict[str, float | int]] = {}
_LOGIN_CHALLENGES: dict[str, dict[str, float | str | int]] = {}


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


def login_lock_duration(stage: int) -> int:
    return {1: 15 * 60, 2: 60 * 60, 3: 24 * 60 * 60}.get(stage, 24 * 60 * 60)


def login_limit_status(email: str | None = None, ip: str | None = None) -> tuple[bool, int]:
    key = login_limit_key(email, ip)
    now = time.time()

    lock = _LOGIN_LOCKS.get(key)
    if lock:
        until = float(lock.get("until") or 0)
        if until > now:
            return True, max(1, int(until - now))
        _LOGIN_LOCKS.pop(key, None)

    entries = prune_login_failures(_LOGIN_FAILURES.get(key, []), now)
    _LOGIN_FAILURES[key] = entries

    return False, 0


def record_login_failure(email: str | None = None, ip: str | None = None) -> tuple[bool, int]:
    key = login_limit_key(email, ip)
    now = time.time()
    entries = prune_login_failures(_LOGIN_FAILURES.get(key, []), now)
    entries.append(now)
    if len(entries) < LOGIN_LIMIT_MAX_FAILURES:
        _LOGIN_FAILURES[key] = entries
        return False, 0

    stage = int((_LOGIN_LOCKS.get(key) or {}).get("stage") or 0) + 1
    if stage > 3:
        stage = 3
    duration = login_lock_duration(stage)
    _LOGIN_LOCKS[key] = {
        "stage": stage,
        "until": now + duration,
    }
    _LOGIN_FAILURES[key] = []
    return True, duration


def clear_login_failures(email: str | None = None, ip: str | None = None) -> None:
    _LOGIN_FAILURES.pop(login_limit_key(email, ip), None)
    _LOGIN_LOCKS.pop(login_limit_key(email, ip), None)
    _LOGIN_CHALLENGES.pop(login_limit_key(email, ip), None)


def get_login_challenge(email: str | None = None, ip: str | None = None) -> dict[str, str]:
    key = login_limit_key(email, ip)
    now = time.time()
    existing = _LOGIN_CHALLENGES.get(key)
    if existing and float(existing.get("expires_at") or 0) > now:
        return {
            "question": str(existing.get("question") or ""),
            "id": str(existing.get("id") or ""),
        }

    left = secrets.randbelow(9) + 1
    right = secrets.randbelow(9) + 1
    challenge_id = secrets.token_hex(8)
    question = f"What is {left} + {right}?"
    _LOGIN_CHALLENGES[key] = {
        "id": challenge_id,
        "question": question,
        "answer": str(left + right),
        "expires_at": now + 15 * 60,
    }
    return {"question": question, "id": challenge_id}


def verify_login_challenge(email: str | None = None, ip: str | None = None, answer: str | None = None) -> bool:
    key = login_limit_key(email, ip)
    challenge = _LOGIN_CHALLENGES.get(key)
    if not challenge:
        return True

    if float(challenge.get("expires_at") or 0) < time.time():
        _LOGIN_CHALLENGES.pop(key, None)
        return False

    expected = str(challenge.get("answer") or "").strip()
    provided = str(answer or "").strip()
    return bool(expected and provided and secrets.compare_digest(expected, provided))


def is_challenge_required(email: str | None = None, ip: str | None = None) -> bool:
    key = login_limit_key(email, ip)
    challenge = _LOGIN_CHALLENGES.get(key)
    if challenge and float(challenge.get("expires_at") or 0) > time.time():
        return True

    failures = prune_login_failures(_LOGIN_FAILURES.get(key, []), time.time())
    return len(failures) >= 3


def is_local_host(hostname: str | None) -> bool:
    hostname = (hostname or "").split(":", 1)[0].lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def cookie_secure_flag() -> bool:
    return not is_local_host(request.host)


def set_refresh_cookie(response, refresh_token: str, remember_me: bool = True) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE if remember_me else None,
        httponly=True,
        secure=cookie_secure_flag(),
        samesite="Strict",
        path="/",
    )
    response.set_cookie(
        REMEMBER_COOKIE_NAME,
        "1" if remember_me else "0",
        max_age=REFRESH_COOKIE_MAX_AGE if remember_me else None,
        httponly=False,
        secure=cookie_secure_flag(),
        samesite="Strict",
        path="/",
    )


def set_remember_cookie(response, remember_me: bool) -> None:
    response.set_cookie(
        REMEMBER_COOKIE_NAME,
        "1" if remember_me else "0",
        max_age=REFRESH_COOKIE_MAX_AGE if remember_me else None,
        httponly=False,
        secure=cookie_secure_flag(),
        samesite="Strict",
        path="/",
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path="/",
        samesite="Strict",
    )
    response.delete_cookie(
        REMEMBER_COOKIE_NAME,
        path="/",
        samesite="Strict",
    )


def display_name_from_email(email: str) -> str:
    email = normalize_email(email)
    return email.split("@", 1)[0] if "@" in email else email or "User"


def password_strength_score(password: str) -> int:
    score = 0
    if len(password) >= 6:
        score += 1
    if len(password) >= 10:
        score += 1
    if any(ch.isupper() for ch in password) and any(ch.isdigit() for ch in password):
        score += 1
    if any(not ch.isalnum() for ch in password):
        score += 1
    return score


def is_pwned_password(password: str) -> bool:
    sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = sha1_hash[:5]
    suffix = sha1_hash[5:]

    try:
        request = Request(f"https://api.pwnedpasswords.com/range/{prefix}", headers={"User-Agent": "ClusterTrainer/1.0"})
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
        for line in body.splitlines():
            candidate, *_ = line.split(":", 1)
            if candidate.strip().upper() == suffix:
                return True
    except Exception:
        return False

    return False


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
    if not target_email:
        return None, None

    status, data = supabase_admin_request(f"/admin/users?email={quote(target_email)}")
    if status == 200:
        users = data.get("users") or []
        for user in users:
            if normalize_email(user.get("email")) == target_email:
                return user, None
        if data.get("id") and normalize_email(data.get("email")) == target_email:
            return data, None

    # Fallback: scan first pages (list endpoint may ignore email filter on older stacks).
    page = 1
    while page <= 5:
        status, data = supabase_admin_request(f"/admin/users?page={page}&per_page=200")
        if status != 200:
            return None, data
        users = data.get("users") or []
        if not users:
            break
        for user in users:
            if normalize_email(user.get("email")) == target_email:
                return user, None
        if len(users) < 200:
            break
        page += 1

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
        "cluster": user_metadata.get("cluster") or "",
    }


def app_base_url() -> str:
    configured = (os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


def supabase_error_message(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    return (
        data.get("msg")
        or data.get("error_description")
        or data.get("detail")
        or data.get("message")
        or ""
    )


def is_email_not_confirmed_error(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    code = str(data.get("error_code") or data.get("error") or "").lower()
    message = supabase_error_message(data).lower()
    return "email_not_confirmed" in code or "not confirm" in message


def extract_auth_tokens(data: dict) -> tuple[str | None, str | None, dict]:
    if not isinstance(data, dict):
        return None, None, {}

    session = data.get("session") or {}
    user = data.get("user") or session.get("user") or data
    if not isinstance(user, dict):
        user = {}

    access_token = session.get("access_token") or data.get("access_token") or data.get("token")
    refresh_token = session.get("refresh_token") or data.get("refresh_token") or data.get("refresh")
    return access_token or None, refresh_token or None, user


def user_email_confirmed(user: dict) -> bool:
    if not isinstance(user, dict):
        return False
    return bool(user.get("email_confirmed_at") or user.get("confirmed_at"))


def admin_confirm_user_by_email(email: str) -> bool:
    user, lookup_error = find_supabase_user_by_email(email)
    if lookup_error or not user:
        return False
    if user.get("email_confirmed_at"):
        return True

    user_id = user.get("id")
    if not user_id:
        return False

    status, _ = supabase_admin_request(
        f"/admin/users/{user_id}",
        method="PUT",
        payload={"email_confirm": True},
    )
    return status == 200


def password_signin(email: str, password: str):
    return supabase_request(
        "/token?grant_type=password",
        method="POST",
        payload={"email": email, "password": password},
    )


def try_issue_session_after_signup(email: str, password: str):
    """Dev helper when email confirmation is enabled but SMTP is not configured."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None, None
    if not admin_confirm_user_by_email(email):
        return None, None
    return password_signin(email, password)


def attempt_signin_with_recovery(email: str, password: str) -> tuple[int, dict]:
    """
  Sign in with Supabase. If credentials look wrong but the account exists and is
  unconfirmed, auto-confirm (when service role is configured) and retry once.
  """
    status, data = password_signin(email, password)
    if status == 200:
        return status, data

    if is_email_not_confirmed_error(data):
        return 403, {
            "detail": (
                "Please confirm your email before signing in. "
                "If you did not get a message, tap Resend confirmation email."
            ),
            "requires_email_confirmation": True,
        }

    if not SUPABASE_SERVICE_ROLE_KEY:
        message = supabase_error_message(data) or "Invalid email or password."
        if "invalid" in message.lower() and "credential" in message.lower():
            message = (
                f"{message} If you just signed up, confirm your email first "
                "(or use Resend confirmation email)."
            )
        payload = dict(data) if isinstance(data, dict) else {}
        payload["detail"] = message
        return status, payload

    user, lookup_error = find_supabase_user_by_email(email)
    if lookup_error:
        return status, {
            "detail": supabase_error_message(lookup_error) or "Unable to verify account status.",
        }

    if not user:
        return status, {
            "detail": supabase_error_message(data) or "Invalid email or password.",
        }

    if not user.get("email_confirmed_at"):
        if admin_confirm_user_by_email(email):
            retry_status, retry_data = password_signin(email, password)
            if retry_status == 200:
                return retry_status, retry_data

        return 403, {
            "detail": (
                "Your email is not confirmed yet. "
                "Use Resend confirmation email, then sign in again."
            ),
            "requires_email_confirmation": True,
        }

    return status, {
        "detail": supabase_error_message(data) or "Invalid email or password.",
    }


def auth_response(
    data: dict,
    status_code: int = 200,
    remember_me: bool = True,
    pending_context: str = "signup",
):
    access_token, refresh_token, user = extract_auth_tokens(data)

    if not access_token:
        confirmed = user_email_confirmed(user)
        if pending_context == "signin" and not confirmed:
            detail = (
                "Your email is not confirmed yet. "
                "Use Resend confirmation email, then sign in again."
            )
        elif pending_context == "signin":
            detail = "Sign-in succeeded but no session token was returned. Check Supabase auth settings."
        else:
            detail = (
                "Account created. Confirm your email to finish signing up. "
                "If nothing arrives, check spam or tap Resend confirmation email."
            )

        payload = {
            "detail": detail,
            "requires_email_confirmation": True,
        }
        if user.get("id") or user.get("email"):
            payload["user"] = serialize_user(user)

        response = make_response(jsonify(payload), 202)
        if refresh_token:
            set_refresh_cookie(response, refresh_token, remember_me)
            set_remember_cookie(response, remember_me)
        return response

    response = make_response(jsonify({
        "access_token": access_token,
        "user": serialize_user(user),
    }), status_code)
    if refresh_token:
        set_refresh_cookie(response, refresh_token, remember_me)
        set_remember_cookie(response, remember_me)
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


@app.get("/terms")
def terms():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Terms</title>
      </head>
      <body style="margin:0;min-height:100vh;background:#081415;color:#eef7f7;font-family:Barlow,Arial,sans-serif;padding:32px;line-height:1.6;">
        <main style="max-width:760px;margin:0 auto;">
          <h1>Terms of Service</h1>
          <p>This is a placeholder terms page for Cluster Trainer.</p>
          <p>Replace this with your final legal terms before launch.</p>
        </main>
      </body>
    </html>
    """


@app.get("/privacy")
def privacy():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Privacy</title>
      </head>
      <body style="margin:0;min-height:100vh;background:#081415;color:#eef7f7;font-family:Barlow,Arial,sans-serif;padding:32px;line-height:1.6;">
        <main style="max-width:760px;margin:0 auto;">
          <h1>Privacy Policy</h1>
          <p>This is a placeholder privacy page for Cluster Trainer.</p>
          <p>Replace this with your final privacy policy before launch.</p>
        </main>
      </body>
    </html>
    """


@app.get("/app/index.html")
def app_index():
    return render_template("signon.html")


@app.get("/reset-password")
def reset_password():
    return render_template("signon.html")


@app.get("/app/opening.html")
def opening():
    return render_template("opening.html")


@app.get("/app/dashboard.html")
def dashboard():
    return render_template("dashboard.html")


@app.get("/app/learn.html")
def learn():
    return render_template("learn.html")


@app.get("/app/practicequestions.html")
def practice_questions():
    return render_template("practicequestions.html")


@app.get("/app/practiceroleplays.html")
def practice_roleplays():
    return render_template("practiceroleplays.html")


@app.get("/app/adminpanel.html")
def admin_panel():
    return render_template("adminpanel.html")


@app.get("/app/settings.html")
def settings():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Settings</title>
        <script src="/static/js/common.js"></script>
        <style>
          body {
            margin: 0;
            min-height: 100vh;
            background: #081415;
            color: #eef7f7;
            font-family: Barlow, Arial, sans-serif;
          }
          .settings-shell {
            padding: 28px;
            max-width: 520px;
            margin: 0 auto;
          }
          h1 {
            margin-bottom: 18px;
            font-size: 2rem;
          }
          .settings-section {
            margin-top: 24px;
            padding: 20px;
            border: 1px solid rgba(238,247,247,0.12);
            border-radius: 18px;
            background: rgba(255,255,255,0.04);
          }
          .option-label {
            display: block;
            margin-bottom: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(238,247,247,0.09);
            border-radius: 14px;
            cursor: pointer;
            transition: border-color 200ms ease, background 200ms ease;
          }
          .option-label:hover {
            border-color: rgba(0,194,224,0.35);
            background: rgba(0,194,224,0.08);
          }
          .option-label input {
            margin-right: 14px;
          }
          .save-button {
            margin-top: 18px;
            padding: 12px 18px;
            border: none;
            border-radius: 12px;
            background: #00c2e0;
            color: #081415;
            font-weight: 700;
            cursor: pointer;
          }
          .status {
            margin-top: 14px;
            color: #a3e635;
            min-height: 1.4em;
          }
          .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 18px 28px;
            border-bottom: 1px solid rgba(238,247,247,0.08);
            background: rgba(0,0,0,0.18);
            position: sticky;
            top: 0;
            z-index: 10;
          }
          .app-brand {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            cursor: pointer;
          }
          .topbar-actions {
            display: flex;
            gap: 10px;
            align-items: center;
          }
          .pill {
            border: 1px solid rgba(238,247,247,0.2);
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            color: #eef7f7;
            padding: 8px 14px;
            cursor: pointer;
          }
        </style>
      </head>
      <body>
        <div class="topbar">
          <div class="app-brand">Cluster Trainer</div>
          <div class="topbar-actions">
            <div id="topbar-name">User</div>
            <button class="pill" id="btn-settings" type="button">Settings</button>
            <button class="pill" id="btn-logout" type="button">Log out</button>
          </div>
        </div>
        <main class="settings-shell" id="settings-shell"></main>
        <script>
          const STORAGE_KEYS = {
            competitionTier: 'ct_competitionTier'
          };

          function getSavedTier() {
            try {
              return localStorage.getItem(STORAGE_KEYS.competitionTier) || '';
            } catch (error) {
              return '';
            }
          }

          function setSavedTier(tier) {
            try {
              localStorage.setItem(STORAGE_KEYS.competitionTier, tier);
            } catch (error) {
            }
          }

          function renderSettings() {
            const currentTier = getSavedTier();
            const shell = document.getElementById('settings-shell');
            shell.innerHTML = `
              <h1>Settings</h1>
              <div class="settings-section">
                <p style="margin-bottom: 16px; color: #9cc6c6;">Select the competition tier you are studying for.</p>
                <label class="option-label"><input type="radio" name="competition-tier" value="Districts" ${currentTier === 'Districts' ? 'checked' : ''}>Districts</label>
                <label class="option-label"><input type="radio" name="competition-tier" value="States" ${currentTier === 'States' ? 'checked' : ''}>States</label>
                <label class="option-label"><input type="radio" name="competition-tier" value="ICDC" ${currentTier === 'ICDC' ? 'checked' : ''}>ICDC</label>
                <button class="save-button" id="save-tier">Save Tier</button>
                <div class="status" id="status-message">${currentTier ? `Current selection: ${currentTier}` : 'No competition tier selected yet.'}</div>
              </div>
            `;

            document.getElementById('save-tier').addEventListener('click', () => {
              const selected = document.querySelector('input[name="competition-tier"]:checked');
              if (!selected) {
                document.getElementById('status-message').textContent = 'Please select a tier before saving.';
                return;
              }
              setSavedTier(selected.value);
              document.getElementById('status-message').textContent = 'Settings saved successfully.';
            });
          }

          requireAuth().then((user) => {
            if (!user) return;
            initTopbar(user);
            renderSettings();
          });
        </script>
      </body>
    </html>
    """


@app.post("/auth/oauth/<provider>")
def oauth_start(provider):
    provider = (provider or "").strip().lower()
    if provider not in {"google", "apple"}:
        return jsonify({"detail": "Unsupported sign-in provider."}), 400
    return jsonify({"detail": f"{provider.title()} sign-in is not configured yet."}), 501


@app.post("/auth/signin")
def signin():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    password = payload.get("password") or ""
    remember_me = bool(payload.get("remember_me", True))
    captcha_answer = payload.get("captcha_answer")
    client_ip = get_client_ip()

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

    if is_challenge_required(email, client_ip) and not verify_login_challenge(email, client_ip, captcha_answer):
        challenge = get_login_challenge(email, client_ip)
        return jsonify({
            "detail": "Please complete the challenge and try again.",
            "captcha_required": True,
            "captcha_prompt": challenge["question"],
        }), 429

    limited, retry_after = login_limit_status(email, client_ip)
    if limited:
        challenge = get_login_challenge(email, client_ip)
        return jsonify({
            "detail": "Too many login attempts. Please wait before trying again.",
            "retry_after_seconds": retry_after,
            "captcha_required": True,
            "captcha_prompt": challenge["question"],
        }), 429

    status, data = attempt_signin_with_recovery(email, password)

    if status != 200:
        message = supabase_error_message(data) or "Invalid email or password."
        if data.get("requires_email_confirmation") or is_email_not_confirmed_error(data):
            return jsonify({
                "detail": message,
                "requires_email_confirmation": True,
            }), status if status in (401, 403) else 403
        limited, retry_after = record_login_failure(email, client_ip)
        if limited:
            challenge = get_login_challenge(email, client_ip)
            return jsonify({
                "detail": "Too many login attempts. Please wait before trying again.",
                "retry_after_seconds": retry_after,
                "captcha_required": True,
                "captcha_prompt": challenge["question"],
            }), 429
        if is_challenge_required(email, client_ip):
            challenge = get_login_challenge(email, client_ip)
            return jsonify({
                "detail": message,
                "captcha_required": True,
                "captcha_prompt": challenge["question"],
            }), 401
        return jsonify({"detail": message}), 401

    clear_login_failures(email, client_ip)
    return auth_response(data, remember_me=remember_me, pending_context="signin")


@app.post("/auth/resend-confirmation")
def resend_confirmation():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))

    if not email:
        return jsonify({"detail": "Please enter your email address."}), 400

    status, data = supabase_request(
        "/resend",
        method="POST",
        payload={
            "type": "signup",
            "email": email,
            "redirect_to": f"{app_base_url()}/",
        },
    )

    if status not in (200, 201):
        message = supabase_error_message(data) or "Unable to resend confirmation email."
        return jsonify({"detail": message}), status

    return jsonify({
        "message": (
            "If your account still needs confirmation, a new email was sent. "
            "Check spam and Promotions folders."
        ),
    })


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

    if password_strength_score(password) < 2:
        return jsonify({"detail": "Password is too weak. Use a stronger password."}), 400

    if is_pwned_password(password):
        return jsonify({"detail": "That password has appeared in a data breach. Choose another one."}), 400

    status, data = supabase_request(
        "/signup",
        method="POST",
        payload={
            "email": email,
            "password": password,
            "data": {
                "display_name": display_name or display_name_from_email(email),
            },
            "redirect_to": f"{app_base_url()}/",
        },
    )

    if status not in (200, 201):
        message = supabase_error_message(data) or "Sign up failed."
        return jsonify({"detail": message}), status

    access_token, _, _ = extract_auth_tokens(data)
    if not access_token:
        signin_status, signin_data = try_issue_session_after_signup(email, password)
        if signin_status == 200 and extract_auth_tokens(signin_data)[0]:
            return auth_response(signin_data, status_code=201, remember_me=True, pending_context="signup")

    return auth_response(data, status_code=201, remember_me=True, pending_context="signup")


@app.get("/auth/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    return jsonify({"user": serialize_user(user)})


@app.put("/auth/profile")
def update_profile():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    cluster = str(payload.get("cluster") or "").strip()
    if not cluster:
        return jsonify({"detail": "Cluster is required."}), 400

    status, data = supabase_request(
        "/user",
        method="PUT",
        token=token,
        payload={
            "data": {
                "cluster": cluster,
            }
        },
    )

    if status != 200 or not isinstance(data, dict):
        message = supabase_error_message(data) or "Unable to update profile."
        return jsonify({"detail": message}), status

    return jsonify({"user": serialize_user(data)})


@app.post("/auth/session")
def session_sync():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""
    remember_me = bool(payload.get("remember_me", True))

    if not refresh_token:
        return jsonify({"detail": "Missing refresh token."}), 400

    response = make_response(jsonify({"message": "Session stored."}))
    set_refresh_cookie(response, refresh_token, remember_me)
    set_remember_cookie(response, remember_me)
    return response


@app.post("/auth/refresh")
def refresh_session():
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME) or ""
    remember_me = (request.cookies.get(REMEMBER_COOKIE_NAME) or "1") == "1"

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

    return auth_response(data, remember_me=remember_me)


@app.post("/auth/logout")
def logout():
    response = make_response(jsonify({"message": "Logged out."}), 200)
    clear_refresh_cookie(response)
    return response


@app.post("/auth/signout")
def signout():
    return logout()


@app.post("/auth/forgot-password")
def forgot_password():
    return password_reset_request()


@app.post("/auth/reset-password")
def reset_password_api():
    return password_reset_complete()


@app.post("/auth/password-reset/request")
def password_reset_request():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))

    if not email:
        return jsonify({"detail": "Please enter your email address."}), 400

    existing_user, lookup_error = find_supabase_user_by_email(email)
    if not lookup_error and existing_user:
        redirect_to = f"{request.host_url.rstrip('/')}/reset-password"
        supabase_request(
            "/recover",
            method="POST",
            payload={
                "email": email,
                "redirect_to": redirect_to,
            },
        )

    return jsonify({"message": "If an account exists, a reset link has been sent. Check your email."})


@app.post("/auth/password-reset/complete")
def password_reset_complete():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Missing recovery session."}), 401

    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""

    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters."}), 400

    if password_strength_score(password) < 2:
        return jsonify({"detail": "Password is too weak. Use a stronger password."}), 400

    if is_pwned_password(password):
        return jsonify({"detail": "That password has appeared in a data breach. Choose another one."}), 400

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
