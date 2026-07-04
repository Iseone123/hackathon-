"""Опциональное шифрование JSON-артефактов (гипотезы, фидбэк) at rest."""

from __future__ import annotations

import base64
import json
from typing import Any

from app.config import settings

_ENCRYPT_MARKER = "__encrypted__"


def is_encryption_enabled() -> bool:
    return bool(settings.encrypt_hypotheses_at_rest and settings.data_encryption_key.strip())


def _fernet():
    from cryptography.fernet import Fernet

    key = settings.data_encryption_key.strip()
    if not key:
        raise ValueError("DATA_ENCRYPTION_KEY не задан")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_text(plain: str) -> str:
    token = _fernet().encrypt(plain.encode("utf-8"))
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_text(cipher_b64: str) -> str:
    token = base64.urlsafe_b64decode(cipher_b64.encode("ascii"))
    return _fernet().decrypt(token).decode("utf-8")


def wrap_encrypted_payload(plain: str) -> dict[str, Any]:
    return {_ENCRYPT_MARKER: True, "payload": encrypt_text(plain)}


def unwrap_encrypted_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get(_ENCRYPT_MARKER):
        return data
    plain = decrypt_text(str(data["payload"]))
    return json.loads(plain)


def read_secure_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if isinstance(data, dict) and data.get(_ENCRYPT_MARKER):
        return unwrap_encrypted_payload(data)
    return data


def write_secure_json(data: dict[str, Any]) -> str:
    plain = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if is_encryption_enabled():
        return json.dumps(wrap_encrypted_payload(plain), ensure_ascii=False, indent=2)
    return plain
