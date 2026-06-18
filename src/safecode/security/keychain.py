"""Keychain credential backend (v4.15.2, EXPERIMENTAL).

Stores and retrieves API keys via the keyring library (macOS Keychain,
Linux Secret Service, Windows Credential Manager). Falls back gracefully
when keyring is unavailable.
"""

from __future__ import annotations

import os
import platform
import subprocess
import warnings

_SERVICE_NAME = "safecode-agent"


def _get_keyring() -> object | None:
    """Return the keyring module or None if unavailable."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def _macos_security_available() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["security", "-h"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return result.returncode in {0, 1, 2}
    except (OSError, subprocess.SubprocessError):
        return False


def _macos_store_api_key(provider: str, api_key: str) -> bool:
    try:
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                _SERVICE_NAME,
                "-a",
                f"provider:{provider}",
                "-w",
                api_key,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _macos_get_api_key(provider: str) -> str | None:
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _SERVICE_NAME,
                "-a",
                f"provider:{provider}",
                "-w",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _macos_delete_api_key(provider: str) -> bool:
    try:
        result = subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-s",
                _SERVICE_NAME,
                "-a",
                f"provider:{provider}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return result.returncode in {0, 44}
    except (OSError, subprocess.SubprocessError):
        return False


def store_api_key(provider: str, api_key: str) -> bool:
    """Store an API key for the given provider in the system keychain.

    Returns True on success, False if keyring is unavailable.
    Never raises.
    """
    if os.getenv("SAFECODE_DISABLE_KEYCHAIN") == "1":
        return False
    kr = _get_keyring()
    if kr is None:
        if _macos_security_available():
            return _macos_store_api_key(provider, api_key)
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
    if os.getenv("SAFECODE_DISABLE_KEYCHAIN") == "1":
        return None
    kr = _get_keyring()
    if kr is None:
        return _macos_get_api_key(provider) if _macos_security_available() else None
    try:
        return kr.get_password(_SERVICE_NAME, f"provider:{provider}")
    except Exception:
        return None


def delete_api_key(provider: str) -> bool:
    """Delete the API key for the given provider from the system keychain.

    Returns True if deleted or not present, False on error.
    Never raises.
    """
    if os.getenv("SAFECODE_DISABLE_KEYCHAIN") == "1":
        return False
    kr = _get_keyring()
    if kr is None:
        if _macos_security_available():
            return _macos_delete_api_key(provider)
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
    if os.getenv("SAFECODE_DISABLE_KEYCHAIN") == "1":
        return False
    return _get_keyring() is not None or _macos_security_available()
