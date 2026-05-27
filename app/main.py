import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request


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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_AUTH_URL = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else ""
SUPABASE_API_TIMEOUT = float(os.environ.get("SUPABASE_API_TIMEOUT", "15"))


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


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

    if not access_token:
        return jsonify({
            "user": serialize_user(user),
            "detail": "Check your email to confirm the account before signing in.",
        }), 202

    return jsonify({
        "access_token": access_token,
        "user": serialize_user(user),
    }), status_code


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

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

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
        return jsonify({"detail": message}), 401

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
