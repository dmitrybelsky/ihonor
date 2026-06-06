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
    """Долгоживущие креды для headless-минта токенов.

    service_token + device_id извлекаются разово из перехвата silent_token-запроса
    приложения HonorWorkStation. scope — фиксированный (из перехвата).
    """
    service_token: str
    device_id: str
    scope: str
    x_hn_dt: str  # device token для sync-API заголовка x-hn-dt


class HonorCloudClient:
    def __init__(self, creds: HonorCreds):
        self._c = creds
        self._access_token: str | None = None
        self._s = requests.Session()

    def mint_access_token(self) -> str:
        """grant_type=service_token -> свежий access_token (доказано: 200)."""
        body = {
            "grant_type": "service_token",
            "service_token": self._c.service_token,
            "scope": self._c.scope,
            "device_type": "1",
            "device_id": self._c.device_id,
            "need_code": "true",
        }
        r = self._s.post(
            f"{OAUTH_BASE}/oauth2/v3/silent_token",
            params={"client_id": CLIENT_ID, "cversion": CVERSION},
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Charset": "UTF-8"},
            timeout=15,
        )
        r.raise_for_status()
        token: str = r.json()["access_token"]
        self._access_token = token
        return token

    def _h(self, extra: dict | None = None) -> dict:
        token = self._access_token or self.mint_access_token()
        h = {
            "Authorization": "Bearer " + token,
            "x-hn-dt": self._c.x_hn_dt,
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
