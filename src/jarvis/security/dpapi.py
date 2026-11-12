"""Windows DPAPI wrapper used to encrypt API keys at rest.

DPAPI ties the ciphertext to the current Windows user account. Nothing in this
module ever writes plaintext keys to disk.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger("jarvis.security.dpapi")

CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _make_blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _read_blob(blob: _DataBlob) -> bytes:
    if not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def available() -> bool:
    if ctypes.windll is None:  # pragma: no cover - non-Windows
        return False
    try:
        protect("jarvis")
        return True
    except Exception:  # pragma: no cover - defensive
        return False


def protect(plaintext: str, *, local_machine: bool = False) -> bytes:
    """Encrypt a UTF-8 string. Raises OSError on failure."""
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be str")
    data = plaintext.encode("utf-8")
    blob_in = _make_blob(data)
    blob_out = _DataBlob()
    flags = CRYPTPROTECT_UI_FORBIDDEN
    if local_machine:
        flags |= CRYPTPROTECT_LOCAL_MACHINE
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        flags,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(f"CryptProtectData failed with error {ctypes.Get_last_error()}")
    try:
        return _read_blob(blob_out)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect(blob: bytes) -> str:
    """Decrypt data produced by :func:`protect` for this Windows user."""
    blob_in = _make_blob(blob)
    blob_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed with error {ctypes.Get_last_error()}")
    try:
        return _read_blob(blob_out).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)