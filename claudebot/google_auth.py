"""One-time Google sign-in: `python -m claudebot.google_auth`.

Opens a browser, asks you to allow Gmail and Calendar access, and saves the token ClaudeBot uses.
Run it on a computer with a browser; copy the token to your server if ClaudeBot runs elsewhere.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from .config import load_config
from .google_services import SCOPES


def main() -> None:
    config = load_config()
    if not config.google_credentials_file.exists():
        sys.exit(
            f"{config.google_credentials_file} not found. Download your OAuth client "
            "(Desktop app) JSON from Google Cloud Console and save it there. See README.md."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(config.google_credentials_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    config.google_token_file.parent.mkdir(parents=True, exist_ok=True)
    config.google_token_file.write_text(creds.to_json())
    print(f"Connected. Token saved to {config.google_token_file}")
    print("If ClaudeBot runs on a server, set GOOGLE_TOKEN_JSON there to the contents of that file.")


if __name__ == "__main__":
    main()
