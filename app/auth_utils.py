import hashlib
import os
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import jsonify, make_response, request

from .config import (
    _LOGIN_CHALLENGES,
    _LOGIN_FAILURES,
    _LOGIN_LOCKS,
    LOGIN_LIMIT_MAX_FAILURES,
    LOGIN_LIMIT_WINDOW_SECONDS,
    REFRESH_COOKIE_MAX_AGE,
    REFRESH_COOKIE_NAME,
    REMEMBER_COOKIE_NAME,
    SUPABASE_SERVICE_ROLE_KEY,
)
from .db import supabase_admin_request, supabase_request, supabase_rest_request


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


def login_limit_status(
    email: str | None = None, ip: str | None = None
) -> tuple[bool, int]:
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


def record_login_failure(
    email: str | None = None, ip: str | None = None
) -> tuple[bool, int]:
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


def get_login_challenge(
    email: str | None = None, ip: str | None = None
) -> dict[str, str]:
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


def verify_login_challenge(
    email: str | None = None, ip: str | None = None, answer: str | None = None
) -> bool:
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
        request = Request(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            headers={"User-Agent": "ClusterTrainer/1.0"},
        )
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
        for line in body.splitlines():
            candidate, *_ = line.split(":", 1)
            if candidate.strip().upper() == suffix:
                return True
    except Exception:
        return False

    return False


def get_profile(user_id: str, token: str) -> dict:
    """Fetch a user's full profile row from the profiles table."""
    status, data = supabase_rest_request(
        "/profiles",
        token=token,
        params={"id": f"eq.{user_id}", "select": "*", "limit": "1"},
    )
    if status == 200 and isinstance(data, list) and data:
        return data[0]
    return {}


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


def serialize_user(user: dict, profile: dict | None = None) -> dict:
    user_metadata = user.get("user_metadata") or {}
    p = profile or {}

    display_name = (
        p.get("display_name")
        or user.get("display_name")
        or user_metadata.get("display_name")
        or user_metadata.get("full_name")
        or user_metadata.get("name")
        or display_name_from_email(user.get("email", ""))
    )

    return {
        "id": user.get("id"),
        "email": user.get("email") or "",
        "display_name": display_name,
        "competition_tier": p.get("competition_tier")
        or user_metadata.get("competition_tier")
        or "districts",
        "default_cluster": p.get("default_cluster")
        or user_metadata.get("default_cluster")
        or "",
        "session_time_pref": p.get("session_time_pref")
        or user_metadata.get("session_time_pref")
        or "morning",
        "randomize_clusters": bool(
            p.get("randomize_clusters")
            or user_metadata.get("randomize_clusters")
            or False
        ),
        "theme": p.get("theme") or user_metadata.get("theme") or "dark",
        "study_goal_minutes": int(
            p.get("study_goal_minutes") or user_metadata.get("study_goal_minutes") or 30
        ),
        "study_goal_kpis": int(
            p.get("study_goal_kpis") or user_metadata.get("study_goal_kpis") or 5
        ),
        "notifications": {
            "session_reminders": bool(p.get("notif_session_reminders", True)),
            "weekly_progress": bool(p.get("notif_weekly_progress", True)),
            "admin_announcements": bool(p.get("notif_admin_announcements", False)),
            "competition_countdown": bool(p.get("notif_competition_countdown", True)),
        },
        "privacy": {
            "track_progress": bool(p.get("privacy_track_progress", True)),
        },
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

    access_token = (
        session.get("access_token") or data.get("access_token") or data.get("token")
    )
    refresh_token = (
        session.get("refresh_token") or data.get("refresh_token") or data.get("refresh")
    )
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
            "detail": supabase_error_message(lookup_error)
            or "Unable to verify account status.",
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

    response = make_response(
        jsonify(
            {
                "access_token": access_token,
                "user": serialize_user(user),
            }
        ),
        status_code,
    )
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


def is_admin(user: dict | None) -> bool:
    from .config import ADMIN_EMAILS

    if not user:
        return False
    return (user.get("email") or "").strip().lower() in ADMIN_EMAILS
