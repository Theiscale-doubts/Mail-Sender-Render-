"""
Configuration + credential storage.

- Secrets (Gmail address + App Password) live in environment variables,
  loaded from a local .env file. On Render you set the SAME variable names
  as secret env vars in the dashboard -> nothing changes in the code.
- Non-secret settings (sheet URLs, email templates, stats) live in config.json.
"""
import os
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
ENV_FILE = BASE / ".env"


def _manual_load_env(path: Path) -> None:
    """Minimal .env loader used when python-dotenv isn't installed.
    Parses KEY=VALUE lines, ignores blanks/comments, strips surrounding quotes.
    Existing real env vars (e.g. set in the Render dashboard) win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# Load the .env that sits next to this file, regardless of the working
# directory you launch from. Prefer python-dotenv; fall back to the manual
# parser so credentials load even if the package isn't installed.
try:
    from dotenv import load_dotenv, set_key
    load_dotenv(ENV_FILE)
except Exception:  # python-dotenv not available
    _manual_load_env(ENV_FILE)

    def set_key(env_path, key, value):  # type: ignore
        """Fallback writer: rewrite the .env file with the updated key."""
        p = Path(env_path)
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        out, found = [], False
        for ln in lines:
            if ln.strip().startswith(f"{key}=") or ln.strip().startswith(f"{key} ="):
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(ln)
        if not found:
            out.append(f"{key}={value}")
        p.write_text("\n".join(out) + "\n", encoding="utf-8")

DEFAULT_TEMPLATES = {
    "basic": {
        "subject": "Weekly Update - {date}",
        "body": ("Dear {Name},\n\nThis is your weekly update.\n\n"
                 "Write your message here.\n\nRegards,\nThe Team"),
    },
    "main": {
        "subject": "Important Notice - {date}",
        "body": ("Hello {Name},\n\nWe have an important update for you.\n\n"
                 "Write your message here.\n\nThank you,\nAdmin"),
    },
}

# Only templates + stats are persisted to config.json.
# Sheet URLs live ONLY in the environment (.env / Render) -> single source of
# truth, so editing .env always takes effect and nothing can shadow it.
DEFAULTS = {
    "basic_subject": DEFAULT_TEMPLATES["basic"]["subject"],
    "basic_body": DEFAULT_TEMPLATES["basic"]["body"],
    "main_subject": DEFAULT_TEMPLATES["main"]["subject"],
    "main_body": DEFAULT_TEMPLATES["main"]["body"],
    "stats": {"sent": 0, "failed": 0, "batches": 0},
}
_PERSIST_KEYS = set(DEFAULTS) | {"stats"}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg["stats"] = dict(DEFAULTS["stats"])
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k in DEFAULTS:
                if k in data and k != "stats":
                    cfg[k] = data[k]
            cfg["stats"] = {**DEFAULTS["stats"], **data.get("stats", {})}
        except Exception:
            pass
    # URLs always come straight from the environment — never config.json.
    cfg["basic_url"] = os.environ.get("BASIC_SHEET_URL", "").strip()
    cfg["main_url"] = os.environ.get("MAIN_SHEET_URL", "").strip()
    return cfg


def save_config(cfg: dict) -> None:
    """Persist only templates + stats; URLs are never written here."""
    out = {k: cfg[k] for k in _PERSIST_KEYS if k in cfg}
    CONFIG_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def get_credentials():
    """Returns (email, app_password) from environment (loaded from .env / Render)."""
    return (os.environ.get("GMAIL_ADDRESS", "").strip(),
            os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip())


def save_credentials(email: str, password: str) -> None:
    """
    Write credentials to the local .env file AND the live process environment.
    On Render you instead set GMAIL_ADDRESS / GMAIL_APP_PASSWORD in the
    dashboard's Environment tab (this function is for local convenience).
    """
    email = (email or "").strip()
    password = (password or "").replace(" ", "").strip()
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    set_key(str(ENV_FILE), "GMAIL_ADDRESS", email)
    set_key(str(ENV_FILE), "GMAIL_APP_PASSWORD", password)
    os.environ["GMAIL_ADDRESS"] = email
    os.environ["GMAIL_APP_PASSWORD"] = password


def save_urls(basic_url=None, main_url=None) -> None:
    """
    Write the sheet URLs to .env AND the live process environment, so a change
    takes effect immediately (no restart). On Render set BASIC_SHEET_URL /
    MAIN_SHEET_URL in the dashboard's Environment tab.
    """
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    if basic_url is not None:
        basic_url = basic_url.strip()
        set_key(str(ENV_FILE), "BASIC_SHEET_URL", basic_url)
        os.environ["BASIC_SHEET_URL"] = basic_url
    if main_url is not None:
        main_url = main_url.strip()
        set_key(str(ENV_FILE), "MAIN_SHEET_URL", main_url)
        os.environ["MAIN_SHEET_URL"] = main_url


def record_stats(cfg: dict, sent: int, failed: int) -> None:
    cfg["stats"]["sent"] += sent
    cfg["stats"]["failed"] += failed
    cfg["stats"]["batches"] += 1
    save_config(cfg)
