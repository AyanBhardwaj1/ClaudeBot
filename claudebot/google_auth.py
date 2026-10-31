"""Google sign-in from a computer with a browser: `python -m claudebot google`.

Most people don't need this: send /connect to ClaudeBot and sign in from your phone. This is
the alternative for running ClaudeBot on your own computer.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from .config import load_config
from .google_connect import client_file, write_private
from .google_services import SCOPES


def main() -> None:
    config = load_config()
    path = client_file(config)
    if path is None:
        sys.exit(
            f"{config.google_credentials_file} not found. Download your OAuth client "
            "(Desktop app) JSON from Google Cloud Console and save it there. See README.md."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    write_private(config.google_token_file, creds.to_json())
    print(f"Connected. Token saved to {config.google_token_file}")


if __name__ == "__main__":
    main()
