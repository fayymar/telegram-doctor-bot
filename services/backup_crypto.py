"""
Шифрование резервных копий открытым ключом: X25519 + HKDF-SHA256 + AES-256-GCM.

Отдельный модуль без зависимостей от базы, чтобы расшифровывать копии на своём
компьютере (scripts/backup_tool.py) без настроек сервера.
"""
import base64
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_MAGIC = b"SYMEDBK1"
_INFO = b"symed-backup-v1"


def _derive_key(shared: bytes, eph_pub: bytes, recipient_pub: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph_pub + recipient_pub, info=_INFO).derive(shared)


def _raw_public(key: X25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def encrypt(data: bytes, public_key_b64: str) -> bytes:
    """Шифрует данные открытым ключом. Формат: MAGIC | eph_pub(32) | nonce(12) | шифротекст."""
    recipient = X25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    eph = X25519PrivateKey.generate()
    eph_pub = _raw_public(eph.public_key())
    key = _derive_key(eph.exchange(recipient), eph_pub, _raw_public(recipient))
    nonce = secrets.token_bytes(12)
    return _MAGIC + eph_pub + nonce + AESGCM(key).encrypt(nonce, data, _MAGIC)


def decrypt(blob: bytes, private_key_b64: str) -> bytes:
    if not blob.startswith(_MAGIC):
        raise ValueError("not a Symed backup file")
    eph_pub = blob[len(_MAGIC):len(_MAGIC) + 32]
    nonce = blob[len(_MAGIC) + 32:len(_MAGIC) + 44]
    private = X25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    key = _derive_key(private.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub,
                      _raw_public(private.public_key()))
    return AESGCM(key).decrypt(nonce, blob[len(_MAGIC) + 44:], _MAGIC)


def generate_keypair() -> tuple[str, str]:
    """(закрытый, открытый) ключи в base64."""
    private = X25519PrivateKey.generate()
    raw_private = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
    return base64.b64encode(raw_private).decode(), base64.b64encode(_raw_public(private.public_key())).decode()


def is_valid_public_key(public_key_b64: str) -> bool:
    try:
        X25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        return True
    except Exception:
        return False
