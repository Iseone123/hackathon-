"""Тесты безопасности: API-ключи, RBAC, шифрование."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.security.auth import authorize_request, parse_api_keys
from app.security.encryption import read_secure_json, write_secure_json, wrap_encrypted_payload


def test_parse_api_keys_with_roles():
    keys = parse_api_keys("abc:admin,def:viewer,ghi")
    assert keys["abc"] == "admin"
    assert keys["def"] == "viewer"
    assert keys["ghi"] == "expert"


def test_viewer_cannot_generate():
    with pytest.raises(Exception) as exc:
        authorize_request("POST", "/hypotheses/generate", "viewer")
    assert exc.value.status_code == 403


def test_expert_can_generate():
    authorize_request("POST", "/hypotheses/generate", "expert")


def test_expert_cannot_ingest():
    with pytest.raises(Exception) as exc:
        authorize_request("POST", "/ingest/batch", "expert")
    assert exc.value.status_code == 403


def test_admin_can_ingest():
    authorize_request("POST", "/ingest/batch", "admin")


def test_encrypt_decrypt_roundtrip():
    key = Fernet.generate_key().decode()
    with patch("app.security.encryption.settings") as mock_settings:
        mock_settings.encrypt_hypotheses_at_rest = True
        mock_settings.data_encryption_key = key
        data = {"generation_id": "g1", "hypotheses": []}
        raw = write_secure_json(data)
        restored = read_secure_json(raw)
    assert restored == data
    assert "__encrypted__" in json.loads(raw)


def test_read_plain_json():
    plain = '{"a": 1}'
    assert read_secure_json(plain) == {"a": 1}


def test_wrap_encrypted_payload():
    key = Fernet.generate_key().decode()
    with patch("app.security.encryption.settings") as mock_settings:
        mock_settings.data_encryption_key = key
        wrapped = wrap_encrypted_payload('{"x": 1}')
    assert wrapped["__encrypted__"] is True
    assert wrapped["payload"]
