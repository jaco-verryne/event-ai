"""Google sign-in, services and request execution for the Calendar and Gmail tools (CLAUDE.md 10.5)."""

from pathlib import Path

import google_auth_httplib2
import httplib2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from eventai.agent.tools import TIMEOUT_SECONDS, ToolError, retrying
from eventai.config import ROOT, load_settings

# The agent reads only. The write scopes belong to seed/seed_google.py and its own token file.
AGENT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
SEED_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.insert",
    # Read too, so that a second seed run finds the emails already there and inserts no copies.
    "https://www.googleapis.com/auth/gmail.readonly",
]
RETRY_STATUS = {429, 500, 502, 503, 504}


def load_credentials(client_secret_file: str | Path, token_file: str | Path, scopes: list[str]) -> Credentials:
    """Use the saved token; refresh it; or sign in once in the browser and save a new token."""
    token_file, client_secret_file = Path(token_file), Path(client_secret_file)
    creds = Credentials.from_authorized_user_file(str(token_file), scopes) if token_file.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # In Testing status a refresh token expires after 7 days: sign in again.
    if not creds or not creds.valid:
        if not client_secret_file.exists():
            raise ToolError(f"{client_secret_file} is missing: create the OAuth desktop client first (CLAUDE.md 10.5)")
        creds = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), scopes).run_local_server(port=0)
    token_file.write_text(creds.to_json())
    return creds


def agent_credentials() -> Credentials:
    """The read-only token for the agent, with the file paths from the config (relative to the repository)."""
    settings = load_settings()
    return load_credentials(ROOT / settings.google_client_secret_file, ROOT / settings.google_token_file,
                            AGENT_SCOPES)


def build_service(api: str, version: str, credentials: Credentials, timeout: int = TIMEOUT_SECONDS):
    http = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=timeout))
    return build(api, version, http=http, cache_discovery=False)


def _retryable(err: BaseException) -> bool:
    if isinstance(err, HttpError):
        return err.resp.status in RETRY_STATUS
    return isinstance(err, (TimeoutError, ConnectionError, httplib2.HttpLib2Error))


def execute(request, what: str):
    """Run one Google API request with retries. A final failure becomes a ToolError."""
    try:
        for attempt in retrying(_retryable):
            with attempt:
                return request.execute()
    except Exception as err:  # noqa: BLE001 - every failure is a tool failure for the run
        raise ToolError(f"{what} failed: {err}") from err
