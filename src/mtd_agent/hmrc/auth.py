"""HMRC sandbox OAuth 2.0 token management.

Ported from the AIAccountant prototype, re-pointed at `config.Settings` so the
**sandbox guard is unavoidable** — client id/secret and base URL come from the
validated settings, never raw env. Access/refresh tokens are runtime state
(rotated on every refresh), so they live in `.env` and are read/written here.

One-time setup: the user runs the interactive token flow once to populate
`HMRC_ACCESS_TOKEN` / `HMRC_REFRESH_TOKEN` / `HMRC_TOKEN_EXPIRES_AT`. Thereafter
`get_access_token()` silently refreshes ahead of expiry.
"""

from __future__ import annotations

import os
import time

import httpx
from dotenv import find_dotenv, set_key

from mtd_agent.config import Settings, assert_sandbox

from .errors import HmrcAuthError, HmrcSystemError

# Refresh if the token expires within this many seconds.
_REFRESH_SKEW = 300


def _env_path() -> str:
    """Locate the .env to persist rotated tokens into (cwd-anchored)."""
    found = find_dotenv(usecwd=True)
    return found or os.path.join(os.getcwd(), ".env")


def _write_env(key: str, value: str) -> None:
    """Persist a key/value to .env and update the live process environment."""
    set_key(_env_path(), key, value)
    os.environ[key] = value


def _token_endpoint(settings: Settings) -> str:
    return f"{assert_sandbox(settings.hmrc_base_url)}/oauth/token"


def _refresh_access_token(settings: Settings) -> str:
    """Exchange the stored refresh_token for a new access/refresh pair.

    Writes the new tokens back to .env and returns the new access token.
    Raises HmrcAuthError if refresh is impossible (user must re-run the flow).
    """
    refresh_token = os.getenv("HMRC_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        raise HmrcAuthError(
            "HMRC_REFRESH_TOKEN is missing. Run the token flow "
            "(python -m mtd_agent.hmrc.get_token) to authorise."
        )
    if not settings.hmrc_client_id or not settings.hmrc_client_secret:
        raise HmrcAuthError("HMRC_CLIENT_ID / HMRC_CLIENT_SECRET are not set in .env.")

    try:
        response = httpx.post(
            _token_endpoint(settings),
            data={
                "client_id": settings.hmrc_client_id,
                "client_secret": settings.hmrc_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise HmrcSystemError(f"Token endpoint unreachable: {exc}") from exc

    if not response.is_success:
        raise HmrcAuthError(
            f"Token refresh failed: {response.text}. Re-run the token flow.",
            status=response.status_code,
        )

    data = response.json()
    access_token = data["access_token"]
    new_refresh = data.get("refresh_token", refresh_token)
    expires_at = str(int(time.time()) + int(data.get("expires_in", 14400)))

    _write_env("HMRC_ACCESS_TOKEN", access_token)
    _write_env("HMRC_REFRESH_TOKEN", new_refresh)
    _write_env("HMRC_TOKEN_EXPIRES_AT", expires_at)
    return access_token


def get_access_token(settings: Settings | None = None) -> str:
    """Return a valid HMRC Bearer token, refreshing if missing or near expiry."""
    settings = settings or Settings.load()
    token = os.getenv("HMRC_ACCESS_TOKEN", "").strip()
    expires_at = int(os.getenv("HMRC_TOKEN_EXPIRES_AT", "0") or "0")

    placeholder = token in ("", "your_sandbox_access_token_here")
    if placeholder or time.time() > (expires_at - _REFRESH_SKEW):
        token = _refresh_access_token(settings)
    return token
