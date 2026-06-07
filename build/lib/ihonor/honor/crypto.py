"""HONOR Notes cloud — content crypto (вскрыто Phase 0 спайком).

Схема (вскрыта хуками EVP_sm4_*/ECDH_compute_key в libcrypto.1.1):
- Обмен ключа: клиент шлёт свой SM2 pubkey в заголовке x-hn-cl-pbk (DER SPKI).
  Сервер заворачивает working key; клиент получает через GET .../workingKey (hex blob).
- Unwrap: **ECDH(client_priv, server_pub)** (SM2-кривая) → 32-байт shared X →
  SM4-ключ из shared → SM4-decrypt(workingKey blob) → SM4 working key (16 байт).
  (PKEYDEC=0 при capture → НЕ SM2-конверт; ECDH_compute_key давал 32-байт shared.)
- Контент заметки: SM4(working key, note-JSON) → hex → поле `data` в upstream.
  SM4 с 16-байт IV (CBC/CTR; точный режим подтвердить против live-блоба).

ОТКРЫТО (нужен рабочий API-доступ, сейчас 403 WAF/stAuth): точный KDF shared→SM4key
и режим SM4 блоба. Кандидаты в unwrap_working_key() ниже — перебрать против live.

Свой keypair → app keystore НЕ нужен (полностью headless).
"""
from __future__ import annotations

import base64
import os

from gmssl import sm2, sm4
from gmssl.sm3 import sm3_hash

# SM2 (sm2p256v1) параметры
SM2_G = ("32c4ae2c1f1981195f9904466a39c9948fe30bbff2660be1715a4589334c74c7"
         "bc3736a2f4f6779c59bdcee36b692153d0a9877cc62a474002df32e52139f0a0")
SM2_N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
# DER SubjectPublicKeyInfo префикс для SM2 (OID 1.2.156.10197.1.301) + uncompressed point
DER_SPKI_PREFIX = bytes.fromhex("305a301406072a8648ce3d020106092b2403030208010107034200")


def gen_keypair() -> tuple[str, str]:
    """Возвращает (priv_hex64, pub_xy_hex128) на кривой SM2."""
    priv = (int.from_bytes(os.urandom(32), "big") % (SM2_N - 1)) + 1
    priv_hex = "%064x" % priv
    crypt = sm2.CryptSM2(public_key="", private_key=priv_hex)
    pub = crypt._kg(priv, SM2_G)  # priv*G -> point x||y
    return priv_hex, pub


def client_pubkey_header(pub_xy_hex: str) -> str:
    """x-hn-cl-pbk = base64(DER SPKI(04||X||Y))."""
    return base64.b64encode(DER_SPKI_PREFIX + b"\x04" + bytes.fromhex(pub_xy_hex)).decode()


def server_point_from_spki_b64(spki_b64: str) -> str:
    """Извлечь X||Y (hex128) из base64 DER SPKI ответа /publicKey."""
    spki = base64.b64decode(spki_b64)
    return spki[-64:].hex()  # last 64 bytes = X||Y (point без 0x04)


def ecdh_shared(priv_hex: str, server_xy_hex: str) -> bytes:
    """ECDH на SM2: priv * serverPub -> shared X (32 байта)."""
    crypt = sm2.CryptSM2(public_key=server_xy_hex, private_key=priv_hex)
    point = crypt._kg(int(priv_hex, 16), server_xy_hex)
    return bytes.fromhex(point[:64])  # X


def _sm4_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    s = sm4.CryptSM4()
    s.set_key(key, sm4.SM4_DECRYPT)
    return s.crypt_ecb(data)


def unwrap_working_key(shared_x: bytes, wk_blob: bytes) -> list[bytes]:
    """Кандидаты unwrap (перебрать против live, см. docstring модуля).

    Возвращает список расшифровок-кандидатов для ручной/авто-валидации
    (валидный = содержит 16-байт ключ / печатаемую структуру).
    """
    sm3_16 = bytes.fromhex(sm3_hash(list(shared_x)))[:16]
    return [
        _sm4_ecb_decrypt(shared_x[:16], wk_blob),
        _sm4_ecb_decrypt(shared_x[16:], wk_blob),
        _sm4_ecb_decrypt(sm3_16, wk_blob),
    ]


def sm4_encrypt_note(working_key: bytes, note_json: str, iv: bytes | None = None) -> str:
    """SM4(working_key, note_json) -> hex (поле data в upstream). Режим уточнить (ECB/CBC)."""
    s = sm4.CryptSM4()
    s.set_key(working_key, sm4.SM4_ENCRYPT)
    data = note_json.encode("utf-8")
    ct = s.crypt_cbc(iv, data) if iv else s.crypt_ecb(data)
    return ct.hex()
