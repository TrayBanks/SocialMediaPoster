import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from utils.logger import logger

# Scopes required to upload videos and set thumbnails
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class YouTubeAuthManager:
    """
    Manages Google OAuth 2.0 credentials for the YouTube Data API v3.

    Token lifecycle:
      1. Load cached token from disk if present.
      2. If the token is expired but a refresh_token exists, refresh automatically.
      3. If no token exists (or refresh fails), run the full OAuth browser flow.
      4. Save updated credentials after every change.
    """

    def __init__(self, token_path: str, client_secrets_path: str) -> None:
        self.token_path = token_path
        self.client_secrets_path = client_secrets_path

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_credentials(self) -> Credentials:
        """Return valid credentials, refreshing or re-authorizing as needed."""
        creds = self._load_token()

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired YouTube access token…")
            try:
                creds.refresh(Request())
                self._save_token(creds)
                logger.info("YouTube token refreshed successfully.")
                return creds
            except Exception as exc:
                logger.warning(f"Token refresh failed ({exc}). Re-running OAuth flow.")

        # Full OAuth flow
        creds = self._run_oauth_flow()
        self._save_token(creds)
        return creds

    def force_reauth(self) -> Credentials:
        """Delete any cached token and force a new OAuth browser flow."""
        token_file = Path(self.token_path)
        if token_file.exists():
            token_file.unlink()
            logger.info("Cleared cached YouTube token.")
        creds = self._run_oauth_flow()
        self._save_token(creds)
        return creds

    # ── Private helpers ────────────────────────────────────────────────────────

    def _run_oauth_flow(self) -> Credentials:
        logger.info("Opening browser for YouTube OAuth authorization…")
        flow = InstalledAppFlow.from_client_secrets_file(
            self.client_secrets_path, scopes=SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        logger.info("YouTube authorization successful.")
        return creds

    def _save_token(self, creds: Credentials) -> None:
        token_file = Path(self.token_path)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(self.token_path, 0o600)
        logger.info(f"YouTube token saved to '{self.token_path}'.")

    def _load_token(self) -> Credentials | None:
        token_file = Path(self.token_path)
        if not token_file.exists():
            return None
        try:
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            return creds
        except Exception as exc:
            logger.warning(f"Could not load YouTube token: {exc}")
            return None
