import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import Config
from .secure_files import file_lock, write_private


def _load(config: Config) -> Optional[Credentials]:
    if not os.path.exists(config.token_file):
        return None
    try:
        return Credentials.from_authorized_user_file(config.token_file, config.scopes)
    except Exception:
        return None


def get_creds(config: Config) -> Credentials:
    """Get OAuth credentials, refreshing or running the auth flow if needed.

    The token file is rewritten atomically, readable by the owner only, and a
    lock serialises refreshes so concurrent tool calls and bulk workers cannot
    corrupt it or burn the refresh token twice.
    """
    creds = _load(config)
    if creds and creds.valid:
        return creds

    with file_lock(config.token_file):
        # Another thread/process may have refreshed while we waited.
        creds = _load(config)
        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not os.path.exists(config.client_secrets_file):
                raise FileNotFoundError(
                    f"Client secrets file not found at {config.client_secrets_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.client_secrets_file, config.scopes
            )
            creds = flow.run_local_server(port=0)

        write_private(config.token_file, creds.to_json())

    return creds
