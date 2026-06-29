"""One-time OAuth 2.0 Authorization Code flow for the HMRC sandbox.

Run once to authorise:  python -m mtd_agent.hmrc.get_token

Starts a local callback server, opens the HMRC sandbox authorisation page, you
log in with a SANDBOX TEST USER, HMRC redirects back with an auth code, and the
code is exchanged for tokens written into .env. Thereafter `auth.get_access_token`
refreshes silently.

The redirect URI (default http://localhost:8080/callback) MUST be registered on
your HMRC sandbox app. Override with HMRC_REDIRECT_URI in .env. Sandbox-only: the
token exchange goes through config.assert_sandbox.
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlparse

import httpx

from mtd_agent.config import Settings
from mtd_agent.hmrc.auth import _token_endpoint, _write_env

# Sandbox authorisation endpoint (separate host from the API base).
AUTH_URL = "https://test-www.tax.service.gov.uk/oauth/authorize"
DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "read:vat write:vat"

_result: dict = {}

_HTML_OK = b"<html><body style='font-family:sans-serif;padding:2em'><h2 style='color:green'>Authorisation successful</h2><p>You can close this tab and return to the terminal.</p></body></html>"  # noqa: E501
_HTML_ERR = b"<html><body style='font-family:sans-serif;padding:2em'><h2 style='color:red'>Authorisation failed</h2><p>Check the terminal.</p></body></html>"  # noqa: E501


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        qs = parse_qs(urlparse(self.path).query)
        if "code" in qs:
            _result["code"] = qs["code"][0]
            self._respond(200, _HTML_OK)
        elif "error" in qs:
            _result["error"] = qs.get("error_description", qs.get("error", ["Unknown"]))[0]
            self._respond(400, _HTML_ERR)
        else:
            self._respond(404, b"Not found")

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):  # silence access logs
        pass


def main() -> int:
    settings = Settings.load()
    if not (settings.hmrc_client_id and settings.hmrc_client_secret):
        print("HMRC_CLIENT_ID / HMRC_CLIENT_SECRET not set in .env.")
        return 1

    redirect_uri = settings.hmrc_redirect_uri or DEFAULT_REDIRECT_URI
    port = urlparse(redirect_uri).port or 8080

    print("HMRC sandbox OAuth setup")
    print(f"Redirect URI: {redirect_uri}  (must be registered on your sandbox app)\n")

    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # HMRC compares redirect_uri as a raw string, so do not percent-encode it.
    encoded_scope = quote(SCOPE, safe=" ").replace(" ", "+")
    url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={settings.hmrc_client_id}"
        f"&scope={encoded_scope}"
        f"&redirect_uri={redirect_uri}"
    )
    print("Opening the authorisation page — log in with your SANDBOX TEST USER.")
    print(f"If the browser does not open, visit:\n  {url}\n")
    webbrowser.open(url)

    print("Waiting for the HMRC redirect ", end="", flush=True)
    for _ in range(120):
        if _result:
            break
        time.sleep(1)
        print(".", end="", flush=True)
    print()
    server.shutdown()

    if "error" in _result:
        print(f"HMRC returned an error: {_result['error']}")
        return 1
    if "code" not in _result:
        print(f"Timed out. Ensure '{redirect_uri}' is registered on the sandbox app.")
        return 1

    resp = httpx.post(
        _token_endpoint(settings),
        data={
            "grant_type": "authorization_code",
            "client_id": settings.hmrc_client_id,
            "client_secret": settings.hmrc_client_secret,
            "code": _result["code"],
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if not resp.is_success:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        return 1

    data = resp.json()
    _write_env("HMRC_ACCESS_TOKEN", data["access_token"])
    _write_env("HMRC_REFRESH_TOKEN", data.get("refresh_token", ""))
    _write_env("HMRC_TOKEN_EXPIRES_AT", str(int(time.time()) + int(data.get("expires_in", 14400))))
    print("\nSuccess — tokens written to .env. You can now run: python -m mtd_agent.cli demo --live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
