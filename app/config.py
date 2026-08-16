import os
from pathlib import Path

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


def first_env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


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
SUPABASE_REST_URL = f"{SUPABASE_URL}/rest/v1" if SUPABASE_URL else ""

SUPABASE_API_TIMEOUT = float(os.environ.get("SUPABASE_API_TIMEOUT", "6"))
GROQ_API_KEY = first_env_value("GROQ_API_KEY")
GROQ_API_TIMEOUT = float(os.environ.get("GROQ_API_TIMEOUT", "60"))
GEMINI_API_KEY = first_env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip() or "gemini-3.6-flash"
GEMINI_API_TIMEOUT = float(os.environ.get("GEMINI_API_TIMEOUT", "60"))
MISTRAL_API_KEY = first_env_value("MISTRAL_API_KEY")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
MISTRAL_API_TIMEOUT = float(os.environ.get("MISTRAL_API_TIMEOUT", "60"))
CLOUDFLARE_API_KEY = first_env_value("CLOUDFLARE_API_KEY", "CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = first_env_value("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_MODEL = os.environ.get(
    "CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
).strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
CLOUDFLARE_API_TIMEOUT = float(os.environ.get("CLOUDFLARE_API_TIMEOUT", "60"))
AI_MAX_CONCURRENT_REQUESTS = max(1, int(os.environ.get("AI_MAX_CONCURRENT_REQUESTS", "2")))
AI_PROVIDER_RETRIES = max(0, int(os.environ.get("AI_PROVIDER_RETRIES", "1")))
AI_RETRY_BASE_SECONDS = max(0.1, float(os.environ.get("AI_RETRY_BASE_SECONDS", "1")))
LOGIN_LIMIT_MAX_FAILURES = int(os.environ.get("LOGIN_LIMIT_MAX_FAILURES", "5"))
LOGIN_LIMIT_WINDOW_SECONDS = int(os.environ.get("LOGIN_LIMIT_WINDOW_SECONDS", "900"))
LOGIN_LIMIT_COOLDOWN_SECONDS = int(
    os.environ.get("LOGIN_LIMIT_COOLDOWN_SECONDS", "900")
)
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME", "ct_refresh_token")
REMEMBER_COOKIE_NAME = os.environ.get("REMEMBER_COOKIE_NAME", "ct_remember_me")
REFRESH_COOKIE_MAX_AGE = int(
    os.environ.get("REFRESH_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30))
)

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "kreesha.patel0831@gmail.com").split(",")
}

_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_LOCKS: dict[str, dict[str, float | int]] = {}
_LOGIN_CHALLENGES: dict[str, dict[str, float | str | int]] = {}
