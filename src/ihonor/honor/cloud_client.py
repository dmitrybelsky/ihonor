"""HONOR Notes Cloud Sync — headless REST-клиент (вскрыто Phase 0 спайком).

Доказано headless БЕЗ приложения:
- auth: mint access_token через grant_type=service_token (silent_token),
- API: GET /sync/notepad/version, publicKey, и т.д. на space-dra.cloud.hihonorcloud.com.

Секреты (service_token, device_id) НЕ хардкодятся — читаются из creds-файла
(вне репозитория). Получить их разово: перехват silent_token-запроса приложения
(см. docs/spike/honor-findings.md) ИЛИ полноценный HONOR ID OAuth (отдельно).

ОСТАЁТСЯ реализовать (см. findings): unwrap workingKey (ECDH+SM4 KDF) + SM4-контент +
формат note-JSON. Это закрывает write end-to-end.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import requests

OAUTH_BASE = "https://hnoauth-login-dra.cloud.honor.com"
SYNC_BASE = "https://space-dra.cloud.hihonorcloud.com"
CLIENT_ID = "211059920"
CVERSION = "win_HnID_4.0.4.001"
SDK_VER = "P9.0.0.301"


@dataclass
class HonorCreds:
    """Долгоживущие креды для headless-доступа.

    silent_token_body — полное form-тело перехваченного silent_token-запроса
    (grant_type=service_token&service_token=...&device_id=...&scope=...), извлекается
    разово. device_id — dvID/deviceId устройства. Этого достаточно для headless auth+API.
    """
    silent_token_body: str
    device_id: str


class HonorCloudClient:
    """Headless-клиент. Auth-цепочка (вскрыта Phase 0, version=200 без app):
      1. silent_token(service_token) -> access_token
      2. POST space-dra /auth?deviceId=..&activation=true (Bearer) -> deviceTicket
      3. ВСЕ /sync/notepad/* с заголовком x-hn-dt = deviceTicket.
    Контент-крипта (workingKey) привязана к ENROLLED device keypair (keystore) — для
    encode/decode тела заметки нужен нативный keystore-вызов (см. findings), НЕ portable.
    """

    def __init__(self, creds: HonorCreds):
        self._c = creds
        self._access_token: str | None = None
        self._device_ticket: str | None = None
        self._s = requests.Session()

    def activate(self) -> str:
        """POST /auth?deviceId=..&activation=true -> deviceTicket (= x-hn-dt сессии)."""
        tok = self._access_token or self.mint_access_token()
        r = self._s.post(
            f"{SYNC_BASE}/auth",
            params={"deviceId": self._c.device_id, "activation": "true"},
            headers={
                "Authorization": "Bearer " + tok, "Accept": "*/*",
                "Content-Type": "application/json", "cache-control": "no-cache",
                "pollingTimeout": "60", "sessionTimeout": "60",
                "x-hn-sdkVer": SDK_VER, "x-hn-appVer": SDK_VER,
            },
            data='{"deviceType":"8","pushToken":"PC_"}',
            timeout=15,
        )
        r.raise_for_status()
        ticket: str = r.json()["data"]["deviceTicket"]
        self._device_ticket = ticket
        return ticket

    def mint_access_token(self) -> str:
        """silent_token (grant_type=service_token) -> свежий access_token (доказано: 200)."""
        r = self._s.post(
            f"{OAUTH_BASE}/oauth2/v3/silent_token",
            params={"client_id": CLIENT_ID, "cversion": CVERSION},
            data=self._c.silent_token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Charset": "UTF-8"},
            timeout=15,
        )
        r.raise_for_status()
        token: str = r.json()["access_token"]
        self._access_token = token
        return token

    def _h(self, extra: dict | None = None) -> dict:
        token = self._access_token or self.mint_access_token()
        ticket = self._device_ticket or self.activate()
        h = {
            "Authorization": "Bearer " + token,
            "x-hn-dt": ticket,  # = deviceTicket из /auth (ротируется посессионно)
            "x-hn-sdkVer": SDK_VER,
            "x-hn-appVer": SDK_VER,
            "Accept": "*/*",
        }
        if extra:
            h.update(extra)
        return h

    # --- sync API (read-доказано headless) ---
    def version(self) -> dict:
        r = self._s.get(f"{SYNC_BASE}/sync/notepad/version", headers=self._h(), timeout=15)
        r.raise_for_status()
        return r.json()["data"]

    def server_public_key(self) -> str:
        r = self._s.get(f"{SYNC_BASE}/basic/security/encryption/publicKey", headers=self._h(), timeout=15)
        r.raise_for_status()
        return r.json()["data"]  # base64 DER SPKI (SM2)

    def working_key(self, client_pubkey_b64: str, key_type: int = 1) -> str:
        r = self._s.get(
            f"{SYNC_BASE}/basic/security/encryption/workingKey",
            params={"keyType": key_type},
            headers=self._h({"x-hn-cl-pbk": client_pubkey_b64}),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["data"]  # wrapped working key (hex)

    def pull_notes(self, sync_sn: int = 0) -> dict:
        r = self._s.get(
            f"{SYNC_BASE}/sync/notepad/note/summary",
            params={"syncSn": sync_sn},
            headers=self._h({"x-hn-syncVer": "12"}),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def upstream_notes(self, add: list[dict], update: list[dict] | None = None,
                       remove: list[dict] | None = None) -> dict:
        """POST /sync/notepad/note/upstream — ЗАПИСЬ.

        add[i] = {"data": "<hex SM4(workingKey, noteJSON)>"} (см. findings).
        Требует обрамления lock/end (см. полный поток в findings).
        """
        payload = {"add": add, "update": update or [], "remove": remove or []}
        r = self._s.post(
            f"{SYNC_BASE}/sync/notepad/note/upstream",
            headers=self._h({"x-hn-syncVer": "12", "Content-Type": "application/json;charset=UTF-8"}),
            data=json.dumps(payload),
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
