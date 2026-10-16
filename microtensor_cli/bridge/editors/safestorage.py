from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERSION = b"v10"
SALT = b"saltysalt"
IV = b" " * 16
MAC_ITERATIONS = 1003
LINUX_ITERATIONS = 1
LINUX_PASSWORD = b"peanuts"
DPAPI_PREFIX = b"DPAPI"
NONCE_BYTES = 12


class SafeStorageError(RuntimeError):
    pass


def cbc_key(password: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=SALT, iterations=iterations)
    return kdf.derive(password)


def cbc_encrypt(password: bytes, iterations: int, plaintext: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(cbc_key(password, iterations)), modes.CBC(IV)).encryptor()
    return VERSION + encryptor.update(padded) + encryptor.finalize()


def gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _mac_password(app: str) -> bytes:
    try:
        found = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", f"{app} Safe Storage"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafeStorageError(f"the macOS keychain could not be read ({exc})") from exc
    if found.returncode != 0 or not found.stdout.strip():
        raise SafeStorageError(
            f"no '{app} Safe Storage' entry in the keychain; open {app} once first"
        )
    return found.stdout.strip().encode("utf-8")


def _local_state_key(local_state: Path) -> bytes:
    try:
        held = json.loads(local_state.read_text(encoding="utf-8"))
        encoded = held["os_crypt"]["encrypted_key"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SafeStorageError(
            f"{local_state} has no encryption key; open the editor once first"
        ) from exc
    blob = base64.b64decode(encoded)
    if not blob.startswith(DPAPI_PREFIX):
        raise SafeStorageError(f"{local_state} uses a key format this version cannot read")
    return _unprotect(blob[len(DPAPI_PREFIX) :])


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _unprotect(data: bytes) -> bytes:
        buffer = ctypes.create_string_buffer(data, len(data))
        source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        target = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        ):
            raise SafeStorageError("Windows refused to unlock the editor's encryption key")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)

else:

    def _unprotect(data: bytes) -> bytes:
        raise SafeStorageError("the editor key is protected by Windows and cannot be read here")


def encrypt(app: str, local_state: Path, plaintext: str) -> tuple[bytes, str]:
    data = plaintext.encode("utf-8")
    if sys.platform == "win32":
        return gcm_encrypt(_local_state_key(local_state), data), ""
    if sys.platform == "darwin":
        return cbc_encrypt(_mac_password(app), MAC_ITERATIONS, data), ""
    note = (
        f"On Linux the key is stored the way {app} stores it without a keyring: obfuscated, "
        "not encrypted. Anyone who can read your home directory can read it."
    )
    return cbc_encrypt(LINUX_PASSWORD, LINUX_ITERATIONS, data), note


def buffer_json(blob: bytes) -> str:
    return json.dumps({"type": "Buffer", "data": list(blob)}, separators=(",", ":"))
