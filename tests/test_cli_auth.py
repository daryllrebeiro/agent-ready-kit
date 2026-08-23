"""Unit tests for CLI authentication and credential storage."""

import os
from packages.cli.auth import clear_api_key, get_stored_api_key, save_api_key


def test_auth_credentials_lifecycle():
    test_key = "ark_live_test_1234567890abcdef"
    save_api_key(test_key)

    retrieved = get_stored_api_key()
    assert retrieved == test_key

    cleared = clear_api_key()
    assert cleared is True
    assert get_stored_api_key() is None
