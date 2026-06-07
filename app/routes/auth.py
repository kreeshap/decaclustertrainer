import json
import time

from flask import Blueprint, jsonify, make_response, request

from ..auth_utils import (
    admin_confirm_user_by_email,
    app_base_url,
    attempt_signin_with_recovery,
    auth_response,
    clear_login_failures,
    clear_refresh_cookie,
    display_name_from_email,
    extract_auth_tokens,
    find_supabase_user_by_email,
    get_bearer_token,
    get_client_ip,
    get_current_user,
    get_login_challenge,
    get_profile,
    is_challenge_required,
    is_email_not_confirmed_error,
    is_pwned_password,
    login_limit_status,
    normalize_email,
    password_strength_score,
    record_login_failure,
    serialize_user,
    set_refresh_cookie,
    set_remember_cookie,
    supabase_error_message,
    try_issue_session_after_signup,
    verify_login_challenge,
)
from ..config import REFRESH_COOKIE_NAME, REMEMBER_COOKIE_NAME
from ..db import supabase_admin_request, supabase_request, supabase_rest_request

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/oauth/<provider>")
def oauth_start(provider):
    provider = (provider or "").strip().lower()
    if provider not in {"google", "apple"}:
        return jsonify({"detail": "Unsupported sign-in provider."}), 400
    return jsonify(
        {"detail": f"{provider.title()} sign-in is not configured yet."}
    ), 501


@auth_bp.post("/auth/signin")
def signin():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    password = payload.get("password") or ""
    remember_me = bool(payload.get("remember_me", True))
    captcha_answer = payload.get("captcha_answer")
    client_ip = get_client_ip()

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

    if is_challenge_required(email, client_ip) and not verify_login_challenge(
        email, client_ip, captcha_answer
    ):
        challenge = get_login_challenge(email, client_ip)
        return jsonify(
            {
                "detail": "Please complete the challenge and try again.",
                "captcha_required": True,
                "captcha_prompt": challenge["question"],
            }
        ), 429

    limited, retry_after = login_limit_status(email, client_ip)
    if limited:
        challenge = get_login_challenge(email, client_ip)
        return jsonify(
            {
                "detail": "Too many login attempts. Please wait before trying again.",
                "retry_after_seconds": retry_after,
                "captcha_required": True,
                "captcha_prompt": challenge["question"],
            }
        ), 429

    status, data = attempt_signin_with_recovery(email, password)

    if status != 200:
        message = supabase_error_message(data) or "Invalid email or password."
        if data.get("requires_email_confirmation") or is_email_not_confirmed_error(
            data
        ):
            return jsonify(
                {
                    "detail": message,
                    "requires_email_confirmation": True,
                }
            ), status if status in (401, 403) else 403
        limited, retry_after = record_login_failure(email, client_ip)
        if limited:
            challenge = get_login_challenge(email, client_ip)
            return jsonify(
                {
                    "detail": "Too many login attempts. Please wait before trying again.",
                    "retry_after_seconds": retry_after,
                    "captcha_required": True,
                    "captcha_prompt": challenge["question"],
                }
            ), 429
        if is_challenge_required(email, client_ip):
            challenge = get_login_challenge(email, client_ip)
            return jsonify(
                {
                    "detail": message,
                    "captcha_required": True,
                    "captcha_prompt": challenge["question"],
                }
            ), 401
        return jsonify({"detail": message}), 401

    clear_login_failures(email, client_ip)
    return auth_response(data, remember_me=remember_me, pending_context="signin")


@auth_bp.post("/auth/resend-confirmation")
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

    return jsonify(
        {
            "message": (
                "If your account still needs confirmation, a new email was sent. "
                "Check spam and Promotions folders."
            ),
        }
    )


@auth_bp.post("/auth/signup")
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
        return jsonify(
            {"detail": "Password is too weak. Use a stronger password."}
        ), 400

    if is_pwned_password(password):
        return jsonify(
            {
                "detail": "That password has appeared in a data breach. Choose another one."
            }
        ), 400

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
            return auth_response(
                signin_data, status_code=201, remember_me=True, pending_context="signup"
            )

    return auth_response(
        data, status_code=201, remember_me=True, pending_context="signup"
    )


@auth_bp.get("/auth/me")
def me():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    profile = get_profile(user.get("id", ""), token)
    return jsonify({"user": serialize_user(user, profile)})


@auth_bp.put("/auth/profile")
def update_profile():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    user = get_current_user()  # 1 API call
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    user_id = user.get("id")

    auth_meta: dict = {}
    profile_patch: dict = {}

    # Display name
    display_name = str(payload.get("display_name") or "").strip()
    if display_name:
        auth_meta["display_name"] = display_name
        profile_patch["display_name"] = display_name

    # Boolean preferences
    for bool_field in (
        "randomize_clusters",
        "notif_session_reminders",
        "notif_weekly_progress",
        "notif_admin_announcements",
        "notif_competition_countdown",
        "privacy_track_progress",
    ):
        if bool_field in payload:
            profile_patch[bool_field] = bool(payload[bool_field])

    # Integer preferences
    for int_field in ("study_goal_minutes", "study_goal_kpis"):
        if int_field in payload:
            try:
                profile_patch[int_field] = int(payload[int_field])
            except (TypeError, ValueError):
                pass

    # String preferences
    for str_field in (
        "competition_tier",
        "default_cluster",
        "session_time_pref",
        "theme",
    ):
        if str_field in payload and payload[str_field] is not None:
            profile_patch[str_field] = str(payload[str_field]).strip()

    # Update Supabase auth user_metadata (only if display_name changed)
    if auth_meta:
        supabase_request(
            "/user", method="PUT", token=token, payload={"data": auth_meta}
        )  # 2nd API call (conditional)

    # Upsert profiles table in a single call using merge-duplicates
    if profile_patch and user_id:
        profile_patch["id"] = user_id
        profile_patch["email"] = user.get("email", "")
        supabase_rest_request(
            "/profiles",
            method="POST",
            token=token,
            payload=profile_patch,
            prefer="resolution=merge-duplicates,return=representation",
        )  # 3rd API call — true upsert, no need for separate PATCH

    # Build the response from what we already know — no extra roundtrip
    merged_profile = profile_patch.copy()
    return jsonify({"user": serialize_user(user, merged_profile)})


@auth_bp.post("/auth/session")
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


@auth_bp.post("/auth/refresh")
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


@auth_bp.post("/auth/logout")
def logout():
    response = make_response(jsonify({"message": "Logged out."}), 200)
    clear_refresh_cookie(response)
    return response


@auth_bp.post("/auth/signout")
def signout():
    return logout()


@auth_bp.post("/auth/forgot-password")
def forgot_password():
    return password_reset_request()


@auth_bp.post("/auth/reset-password")
def reset_password_api():
    return password_reset_complete()


@auth_bp.post("/auth/password-reset/request")
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

    return jsonify(
        {
            "message": "If an account exists, a reset link has been sent. Check your email."
        }
    )


@auth_bp.post("/auth/password-reset/complete")
def password_reset_complete():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Missing recovery session."}), 401

    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""

    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters."}), 400

    if password_strength_score(password) < 2:
        return jsonify(
            {"detail": "Password is too weak. Use a stronger password."}
        ), 400

    if is_pwned_password(password):
        return jsonify(
            {
                "detail": "That password has appeared in a data breach. Choose another one."
            }
        ), 400

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


@auth_bp.post("/auth/change-email")
def change_email():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    new_email = normalize_email(payload.get("email"))
    if not new_email:
        return jsonify({"detail": "Please enter a new email address."}), 400

    status, data = supabase_request(
        "/user",
        method="PUT",
        token=token,
        payload={
            "email": new_email,
            "email_redirect_to": f"{app_base_url()}/",
        },
    )

    if status not in (200, 201):
        message = supabase_error_message(data) or "Unable to update email."
        return jsonify({"detail": message}), status

    return jsonify(
        {
            "message": "A confirmation email has been sent to your new address. Click the link to confirm the change."
        }
    )


@auth_bp.post("/auth/change-password")
def change_password():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    new_password = payload.get("new_password") or ""
    confirm_password = payload.get("confirm_password") or ""

    if not new_password:
        return jsonify({"detail": "Please enter a new password."}), 400
    if new_password != confirm_password:
        return jsonify({"detail": "Passwords do not match."}), 400
    if len(new_password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters."}), 400
    if password_strength_score(new_password) < 2:
        return jsonify(
            {
                "detail": "Password is too weak. Use a mix of letters, numbers, and symbols."
            }
        ), 400

    if is_pwned_password(new_password):
        return jsonify(
            {
                "detail": "That password has appeared in a data breach. Choose another one."
            }
        ), 400

    status, data = supabase_request(
        "/user",
        method="PUT",
        token=token,
        payload={"password": new_password},
    )

    if status not in (200, 201):
        message = supabase_error_message(data) or "Unable to update password."
        return jsonify({"detail": message}), status

    return jsonify({"message": "Password updated successfully."})


@auth_bp.delete("/auth/account")
def delete_account():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    user_id = user.get("id")
    if not user_id:
        return jsonify({"detail": "Unable to identify user account."}), 400

    # Delete via admin API
    status, data = supabase_admin_request(f"/admin/users/{user_id}", method="DELETE")
    if status not in (200, 204):
        message = (
            supabase_error_message(data) or "Unable to delete account. Contact support."
        )
        return jsonify({"detail": message}), status

    response = make_response(jsonify({"message": "Account permanently deleted."}))
    clear_refresh_cookie(response)
    return response


@auth_bp.get("/auth/export")
def export_data():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    profile = get_profile(user.get("id", ""), token)
    user_data = serialize_user(user, profile)

    export = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": user_data,
    }

    response = make_response(json.dumps(export, indent=2))
    response.headers["Content-Type"] = "application/json"
    response.headers["Content-Disposition"] = (
        'attachment; filename="cluster_trainer_data.json"'
    )
    return response


@auth_bp.post("/auth/signout-all")
def signout_all():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    # Supabase supports scope=global to revoke all refresh tokens
    supabase_request("/logout?scope=global", method="POST", token=token)

    response = make_response(
        jsonify({"message": "All other sessions have been signed out."})
    )
    return response


@auth_bp.delete("/auth/progress")
def reset_progress():
    token = get_bearer_token()
    if not token:
        return jsonify({"detail": "Unauthorized"}), 401

    user = get_current_user()
    if not user:
        return jsonify({"detail": "Unauthorized"}), 401

    user_id = user.get("id")
    if not user_id:
        return jsonify({"detail": "Unable to identify user."}), 400

    # Delete all progress rows for this user from the user_progress table.
    # Uses the user's own token so RLS enforces ownership.
    status, data = supabase_rest_request(
        "/user_progress",
        method="DELETE",
        token=token,
        params={"user_id": f"eq.{user_id}"},
        prefer="return=minimal",
    )

    if status not in (200, 204):
        message = (
            (data or {}).get("message")
            or (data or {}).get("detail")
            or "Unable to reset progress."
        )
        return jsonify({"detail": message}), status

    return jsonify({"message": "All progress has been reset."})
