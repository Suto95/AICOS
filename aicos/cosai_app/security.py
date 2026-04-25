import base64
import hashlib
import os


def _load_crypto():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing cryptography package. Install with: pip install cryptography") from exc
    return Fernet, InvalidToken


def _fernet_from_env():
    raw = os.getenv("COSAI_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None

    Fernet, _ = _load_crypto()
    key = raw
    # If caller provides a passphrase instead of a fernet key, derive a stable 32-byte key.
    if not raw.startswith("gAAAA") and not raw.endswith("="):
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("utf-8")
    return Fernet(key.encode("utf-8"))


def encrypt_secret(value):
    text = value or ""
    if not text:
        return ""
    f = _fernet_from_env()
    if not f:
        return f"plain::{text}"
    return f"enc::{f.encrypt(text.encode('utf-8')).decode('utf-8')}"


def decrypt_secret(value):
    raw = value or ""
    if not raw:
        return ""
    if raw.startswith("plain::"):
        return raw[len("plain::") :]
    if raw.startswith("enc::"):
        payload = raw[len("enc::") :]
        f = _fernet_from_env()
        if not f:
            raise RuntimeError("COSAI_ENCRYPTION_KEY is required to decrypt stored tokens.")
        _, InvalidToken = _load_crypto()
        try:
            return f.decrypt(payload.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Unable to decrypt token. Check COSAI_ENCRYPTION_KEY.") from exc
    # Legacy plaintext fallback for rows created before hardening.
    return raw
