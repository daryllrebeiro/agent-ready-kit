"""Local CLI authentication and API key credentials management."""

import json
import os
from typing import Any, Dict, Optional

CREDENTIALS_DIR = os.path.expanduser("~/.agentready")
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")


def save_api_key(api_key: str) -> None:
    """Persist API key to user's home directory."""
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    data = {"api_key": api_key.strip()}
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_stored_api_key() -> Optional[str]:
    """Retrieve stored API key or from AGENTREADY_API_KEY environment variable."""
    env_key = os.getenv("AGENTREADY_API_KEY")
    if env_key:
        return env_key.strip()

    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("api_key")
        except Exception:
            return None
    return None


def clear_api_key() -> bool:
    """Remove stored credentials."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            os.remove(CREDENTIALS_FILE)
            return True
        except Exception:
            return False
    return True
