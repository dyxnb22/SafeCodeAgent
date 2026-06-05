"""Keychain credential backend (v4.15.2, EXPERIMENTAL).

Stores and retrieves API keys via the keyring library (macOS Keychain,
Linux Secret Service, Windows Credential Manager). Falls back gracefully
when keyring is unavailable.
"""

from __future__ import annotations

import warnings

_SERVICE_NAME = "safecode-agent"


def _get_keyring() -> object | None:
    """Return the keyring module or None if unavailable."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def store_api_key(provider: str, api_key: str) -> bool:
    """Store an API key for the given provider in the system keychain.

    Returns True on success, False if keyring is unavailable.
    Never raises.
    """
    kr = _get_keyring()
    if kr is None:
        warnings.warn(
            "keyring library not installed. Install with: pip install keyring",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
    try:
        kr.set_password(_SERVICE_NAME, f"provider:{provider}", api_key)
        return True
    except Exception:
        return False


def get_api_key(provider: str) -> str | None:
    """Retrieve the API key for the given provider from the system keychain.

    Returns None if not found or if keyring is unavailable.
    Never raises.
    """
    kr = _get_keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(_SERVICE_NAME, f"provider:{provider}")
    except Exception:
        return None


def delete_api_key(provider: str) -> bool:
    """Delete the API key for the given provider from the system keychain.

    Returns True if deleted or not present, False on error.
    Never raises.
    """
    kr = _get_keyring()
    if kr is None:
        warnings.warn(
            "keyring library not installed. Install with: pip install keyring",
            RuntimeWarning,
            stacklevel=2,
        )
        return False
    try:
        kr.delete_password(_SERVICE_NAME, f"provider:{provider}")
        return True
    except Exception:
        return False


def has_keychain_backend() -> bool:
    """Return True if keyring is available."""
    return _get_keyring() is not None
