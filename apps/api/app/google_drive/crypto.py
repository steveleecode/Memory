import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionError(RuntimeError):
    pass


def encrypt_json(payload: dict[str, Any], key_material: str) -> bytes:
    return _fernet(key_material).encrypt(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def decrypt_json(ciphertext: bytes, key_material: str) -> dict[str, Any]:
    try:
        decoded = _fernet(key_material).decrypt(ciphertext)
    except InvalidToken as exc:
        raise CredentialEncryptionError("stored Google credentials could not be decrypted") from exc
    value = json.loads(decoded.decode("utf-8"))
    if not isinstance(value, dict):
        raise CredentialEncryptionError("stored Google credentials are not a JSON object")
    return value


def _fernet(key_material: str) -> Fernet:
    material = key_material.encode("utf-8")
    if len(material) == 44:
        try:
            base64.urlsafe_b64decode(material)
            return Fernet(material)
        except Exception:
            pass
    digest = hashlib.sha256(material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
