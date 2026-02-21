from __future__ import annotations

import base64
import hashlib
import os
import secrets
import struct
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _sha1_signature(*parts: str) -> str:
    items = [str(p or "") for p in parts]
    raw = "".join(sorted(items)).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()  # noqa: S324


def _b64decode_aes_key(encoding_aes_key: str) -> bytes:
    k = (encoding_aes_key or "").strip()
    if not k:
        raise ValueError("encoding_aes_key is empty")

    # WeCom EncodingAESKey is typically 43 chars base64 without "=" padding.
    try:
        key = base64.b64decode(k + "=", validate=False)
    except Exception as e:
        raise ValueError(f"encoding_aes_key invalid base64: {e}") from None
    if len(key) != 32:
        raise ValueError("encoding_aes_key decoded length must be 32 bytes")
    return key


def _aes_cbc_decrypt(aes_key: bytes, data: bytes) -> bytes:
    iv = aes_key[:16]
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(data) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _aes_cbc_encrypt(aes_key: bytes, data: bytes) -> bytes:
    iv = aes_key[:16]
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    return encryptor.update(padded) + encryptor.finalize()


@dataclass(frozen=True)
class WecomCrypto:
    token: str
    encoding_aes_key: str
    corp_id: str

    def _aes_key(self) -> bytes:
        return _b64decode_aes_key(self.encoding_aes_key)

    def verify_signature(self, *, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> None:
        expected = _sha1_signature(self.token, timestamp, nonce, encrypted)
        if not secrets.compare_digest((msg_signature or "").strip(), expected):
            raise ValueError("invalid msg_signature")

    def decrypt(self, *, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> str:
        encrypted_value = (encrypted or "").strip()
        if not encrypted_value:
            raise ValueError("missing Encrypt")

        self.verify_signature(
            msg_signature=msg_signature,
            timestamp=str(timestamp or ""),
            nonce=str(nonce or ""),
            encrypted=encrypted_value,
        )

        try:
            cipher_bytes = base64.b64decode(encrypted_value, validate=False)
        except Exception as e:
            raise ValueError(f"Encrypt invalid base64: {e}") from None

        plain = _aes_cbc_decrypt(self._aes_key(), cipher_bytes)
        if len(plain) < 20:
            raise ValueError("decrypted payload too short")

        msg_len = struct.unpack("!I", plain[16:20])[0]
        start = 20
        end = start + int(msg_len)
        if end > len(plain):
            raise ValueError("invalid decrypted msg_len")

        msg = plain[start:end]
        corp = plain[end:]
        corp_text = corp.decode("utf-8", errors="replace").strip()
        if corp_text and corp_text != (self.corp_id or "").strip():
            raise ValueError("corp_id mismatch")

        return msg.decode("utf-8", errors="replace")

    def encrypt(self, *, plaintext: str, timestamp: str | None = None, nonce: str | None = None) -> dict[str, str]:
        """
        Returns the encrypted response fields used by WeCom callback:
        - Encrypt
        - MsgSignature
        - TimeStamp
        - Nonce
        """
        ts = (str(timestamp or "")).strip() or str(int(time.time()))
        n = (nonce or "").strip() or secrets.token_hex(8)

        msg = (plaintext or "").encode("utf-8")
        corp = (self.corp_id or "").encode("utf-8")
        raw = os.urandom(16) + struct.pack("!I", len(msg)) + msg + corp
        enc_bytes = _aes_cbc_encrypt(self._aes_key(), raw)
        enc = base64.b64encode(enc_bytes).decode("ascii")

        sig = _sha1_signature(self.token, ts, n, enc)
        return {"Encrypt": enc, "MsgSignature": sig, "TimeStamp": ts, "Nonce": n}
