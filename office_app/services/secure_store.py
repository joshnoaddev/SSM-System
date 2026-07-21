"""Windows DPAPI helpers for small per-user application secrets."""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


class SecureStoreError(RuntimeError):
    """Raised when the operating system cannot protect or restore a secret."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_ENTROPY = b"YWAM Balut SSM sheet sync token v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(
        len(value),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SecureStoreError(
            "Secure token storage requires Windows Data Protection API."
        )


def protect_secret(secret: str) -> str:
    """Encrypt a secret for the current Windows user and return base64 text."""
    _require_windows()
    if not secret:
        return ""

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, input_buffer = _blob(secret.encode("utf-8"))
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    output_blob = _DataBlob()

    succeeded = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "SSM Student Profiling",
        ctypes.byref(entropy_blob),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    # Keep the backing buffers alive through the native call.
    _ = (input_buffer, entropy_buffer)
    if not succeeded:
        raise SecureStoreError(str(ctypes.WinError()))

    try:
        protected = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return base64.urlsafe_b64encode(protected).decode("ascii")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(protected: str) -> str:
    """Decrypt a base64 DPAPI payload for the current Windows user."""
    _require_windows()
    if not protected:
        return ""

    try:
        encrypted = base64.urlsafe_b64decode(protected.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise SecureStoreError("The stored sync token is damaged.") from error

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, input_buffer = _blob(encrypted)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    output_blob = _DataBlob()
    description = ctypes.c_wchar_p()

    succeeded = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        ctypes.byref(description),
        ctypes.byref(entropy_blob),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    _ = (input_buffer, entropy_buffer)
    if not succeeded:
        raise SecureStoreError(
            "Windows could not unlock the stored sync token for this user."
        )

    try:
        plain = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return plain.decode("utf-8")
    finally:
        if description:
            kernel32.LocalFree(description)
        kernel32.LocalFree(output_blob.pbData)
