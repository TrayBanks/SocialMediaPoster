import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── YouTube ────────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS_PATH: str = os.getenv(
    "YOUTUBE_CLIENT_SECRETS_PATH", "client_secrets.json"
)

# ── TikTok ─────────────────────────────────────────────────────────────────────
TIKTOK_CLIENT_KEY: str = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET: str = os.getenv("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI: str = os.getenv(
    "TIKTOK_REDIRECT_URI", "http://localhost:8080/callback"
)

# ── Token storage ──────────────────────────────────────────────────────────────
TOKEN_DIR: str = os.getenv("TOKEN_DIR", "tokens")

# Resolved paths
YOUTUBE_TOKEN_PATH: str = str(Path(TOKEN_DIR) / "youtube_token.json")
TIKTOK_TOKEN_PATH: str = str(Path(TOKEN_DIR) / "tiktok_token.json")


def validate_youtube_config() -> None:
    """Raise ValueError if required YouTube credentials are missing."""
    path = Path(YOUTUBE_CLIENT_SECRETS_PATH)
    if not path.exists():
        raise ValueError(
            f"YouTube client secrets file not found: '{YOUTUBE_CLIENT_SECRETS_PATH}'\n"
            "Download it from Google Cloud Console > APIs & Services > Credentials "
            "and set YOUTUBE_CLIENT_SECRETS_PATH in your .env file."
        )


def validate_tiktok_config() -> None:
    """Raise ValueError if required TikTok credentials are missing."""
    missing = []
    if not TIKTOK_CLIENT_KEY:
        missing.append("TIKTOK_CLIENT_KEY")
    if not TIKTOK_CLIENT_SECRET:
        missing.append("TIKTOK_CLIENT_SECRET")
    if missing:
        raise ValueError(
            f"Missing TikTok credentials: {', '.join(missing)}\n"
            "Set these values in your .env file (see .env.example)."
        )


def ensure_token_dir() -> None:
    """Create the token directory if it does not exist."""
    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
