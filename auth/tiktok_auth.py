import hashlib
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import requests

from utils.logger import logger

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

# Scopes required for the Content Posting API
TIKTOK_SCOPES = "video.upload,video.publish"


class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth redirect code."""

    code: str | None = None
    error: str | None = None

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if "code" in params:
            _CallbackHandler.code = params["code"]
        elif "error" in params:
            _CallbackHandler.error = params.get("error_description", params["error"])

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authorization complete.</h2>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
        )

    def log_message(self, fmt, *args):  # suppress access log noise
        pass


class TikTokAuthManager:
    """
    Manages TikTok OAuth 2.0 (PKCE) credentials for the Content Posting API.

    Token lifecycle:
      1. Load cached token from disk if present.
      2. If access token is near expiry (< 5 min), refresh via refresh_token grant.
      3. If no token exists (or refresh_token is expired), run the full PKCE browser flow.
      4. Save updated token JSON after every change.
    """

    def __init__(
        self,
        token_path: str,
        client_key: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        self.token_path = token_path
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing or re-authorizing as needed."""
        token_data = self._load_token()

        if token_data:
            expires_at = token_data.get("expires_at", 0)
            # Refresh if the token expires within 5 minutes
            if time.time() < expires_at - 300:
                return token_data["access_token"]

            refresh_token = token_data.get("refresh_token")
            if refresh_token:
                logger.info("Refreshing TikTok access token…")
                try:
                    new_data = self._refresh_access_token(refresh_token)
                    self._save_token(new_data)
                    logger.info("TikTok token refreshed successfully.")
                    return new_data["access_token"]
                except Exception as exc:
                    logger.warning(f"TikTok token refresh failed ({exc}). Re-authorizing.")

        token_data = self._run_oauth_flow()
        self._save_token(token_data)
        return token_data["access_token"]

    def force_reauth(self) -> str:
        """Delete any cached token and force a new OAuth browser flow."""
        token_file = Path(self.token_path)
        if token_file.exists():
            token_file.unlink()
            logger.info("Cleared cached TikTok token.")
        token_data = self._run_oauth_flow()
        self._save_token(token_data)
        return token_data["access_token"]

    # ── Private helpers ────────────────────────────────────────────────────────

    def _run_oauth_flow(self) -> dict:
        """Run the PKCE authorization code flow and return token data."""
        # Generate PKCE code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = hashlib.sha256(code_verifier.encode()).digest()
        import base64
        code_challenge_b64 = (
            base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()
        )
        state = secrets.token_urlsafe(16)

        # Build the authorization URL
        params = {
            "client_key": self.client_key,
            "response_type": "code",
            "scope": TIKTOK_SCOPES,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": code_challenge_b64,
            "code_challenge_method": "S256",
        }
        auth_url = TIKTOK_AUTH_URL + "?" + urllib.parse.urlencode(params)

        # Start a local HTTP server to receive the redirect
        _CallbackHandler.code = None
        _CallbackHandler.error = None

        redirect_parsed = urllib.parse.urlparse(self.redirect_uri)
        port = redirect_parsed.port or 8080

        server = HTTPServer(("localhost", port), _CallbackHandler)
        server_thread = Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        logger.info(f"Opening browser for TikTok authorization:\n  {auth_url}")
        webbrowser.open(auth_url)

        # Wait up to 120 seconds for the callback
        server_thread.join(timeout=120)

        if _CallbackHandler.error:
            raise RuntimeError(f"TikTok authorization error: {_CallbackHandler.error}")
        if not _CallbackHandler.code:
            raise RuntimeError(
                "No authorization code received within 120 seconds. "
                "Please ensure the redirect URI in your TikTok app settings matches: "
                f"{self.redirect_uri}"
            )

        code = _CallbackHandler.code
        logger.info("TikTok authorization code received. Exchanging for tokens…")

        # Exchange code for tokens
        resp = requests.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            raise RuntimeError(
                f"TikTok token exchange failed: {data.get('error_description', data['error'])}"
            )

        return self._normalize_token_data(data)

    def _refresh_access_token(self, refresh_token: str) -> dict:
        resp = requests.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            raise RuntimeError(
                f"TikTok refresh failed: {data.get('error_description', data['error'])}"
            )

        return self._normalize_token_data(data)

    @staticmethod
    def _normalize_token_data(data: dict) -> dict:
        """Add computed expires_at so we can check expiry without calling the API."""
        expires_in = data.get("expires_in", 86400)
        data["expires_at"] = int(time.time()) + int(expires_in)
        return data

    def _save_token(self, token_data: dict) -> None:
        token_file = Path(self.token_path)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
        os.chmod(self.token_path, 0o600)
        logger.info(f"TikTok token saved to '{self.token_path}'.")

    def _load_token(self) -> dict | None:
        token_file = Path(self.token_path)
        if not token_file.exists():
            return None
        try:
            return json.loads(token_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not load TikTok token: {exc}")
            return None
