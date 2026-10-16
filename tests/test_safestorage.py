from __future__ import annotations

import json
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from microtensor_cli.bridge.editors.safestorage import (
    IV,
    LINUX_ITERATIONS,
    LINUX_PASSWORD,
    MAC_ITERATIONS,
    buffer_json,
    cbc_encrypt,
    cbc_key,
    gcm_encrypt,
)


def _cbc_decrypt(password: bytes, iterations: int, blob: bytes) -> bytes:
    assert blob[:3] == b"v10"
    decryptor = Cipher(algorithms.AES(cbc_key(password, iterations)), modes.CBC(IV)).decryptor()
    padded = decryptor.update(blob[3:]) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def test_cbc_formats_decrypt_like_chromium() -> None:
    secret = b"mt_sk_test_0123456789abcdef"
    assert (
        _cbc_decrypt(
            LINUX_PASSWORD, LINUX_ITERATIONS, cbc_encrypt(LINUX_PASSWORD, LINUX_ITERATIONS, secret)
        )
        == secret
    )
    assert (
        _cbc_decrypt(b"keychain", MAC_ITERATIONS, cbc_encrypt(b"keychain", MAC_ITERATIONS, secret))
        == secret
    )


def test_gcm_layout_and_buffer_json() -> None:
    key = os.urandom(32)
    blob = gcm_encrypt(key, b"mt_sk_x")
    assert blob[:3] == b"v10" and len(blob) == 3 + 12 + len(b"mt_sk_x") + 16
    assert AESGCM(key).decrypt(blob[3:15], blob[15:], None) == b"mt_sk_x"
    held = json.loads(buffer_json(b"v10"))
    assert held == {"type": "Buffer", "data": [118, 49, 48]}
