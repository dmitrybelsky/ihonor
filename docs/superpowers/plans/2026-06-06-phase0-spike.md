# Phase 0 Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Доказать, что заметки iCloud и HONOR можно читать И писать headless (list/get/create/update/delete) — гейт перед сборкой движка синхронизации.

**Architecture:** Спайк-харнесс на Python. Для каждой стороны: (1) перехват трафика официального клиента для вскрытия endpoints/auth, (2) минимальный клиент против вскрытых endpoints, (3) smoke-проверка 5 операций на реальном аккаунте. Итог — verdict-документ: гейт пройден или нет.

**Tech Stack:** Python 3.11+ · `httpx` · `pyicloud` (только auth/сессия) · `mitmproxy` (перехват) · `pytest` · `keyring`/env для секретов.

> ⚠️ Спайк — разведка недокументированных API. Где endpoints ещё неизвестны, «тест» = runnable smoke-скрипт против реального аккаунта, а не unit-assert. Это намеренно: на этом этапе доказываем существование пути, а не корректность кода.

> 🔐 Безопасность: реальные креды/токены НИКОГДА не коммитим. Только в `.env` (уже в `.gitignore`). Captured-трафик может содержать токены — `captures/` тоже в `.gitignore`.

---

## File Structure

- `pyproject.toml` — проект, зависимости, конфиг pytest
- `.env.example` — шаблон секретов (без значений)
- `src/ihonor/__init__.py`
- `src/ihonor/config.py` — загрузка секретов из env
- `src/ihonor/icloud/auth.py` — auth iCloud + персист сессии
- `src/ihonor/icloud/notes_client.py` — 5 операций над заметками iCloud
- `src/ihonor/honor/notes_client.py` — 5 операций над заметками HONOR
- `scripts/icloud_smoke.py` — smoke 5 операций iCloud
- `scripts/honor_smoke.py` — smoke 5 операций HONOR
- `tests/test_config.py` — unit: загрузка конфига
- `docs/spike/icloud-findings.md` — вскрытые endpoints/auth iCloud
- `docs/spike/honor-findings.md` — вскрытые endpoints/auth HONOR
- `docs/spike/VERDICT.md` — итог гейта
- `captures/` — дампы трафика (в .gitignore, не коммитим)

---

## Task 0: Scaffold проекта

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/ihonor/__init__.py`, `src/ihonor/config.py`, `tests/test_config.py`

- [ ] **Step 1: Написать pyproject.toml**

```toml
[project]
name = "ihonor"
version = "0.0.1"
description = "Двусторонняя синхронизация заметок HONOR <-> iCloud"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pyicloud>=1.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "mitmproxy>=10"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Создать `.env.example`**

```
# iCloud
ICLOUD_APPLE_ID=
ICLOUD_PASSWORD=
# HONOR
HONOR_ID=
HONOR_PASSWORD=
# Шифрование trust-token at-rest (Phase 0: можно пусто)
SECRET_KEY=
```

- [ ] **Step 3: Написать `src/ihonor/config.py`**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    icloud_apple_id: str
    icloud_password: str
    honor_id: str
    honor_password: str

    @staticmethod
    def from_env() -> "Config":
        def req(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise RuntimeError(f"Missing required env var: {key}")
            return val

        return Config(
            icloud_apple_id=req("ICLOUD_APPLE_ID"),
            icloud_password=req("ICLOUD_PASSWORD"),
            honor_id=req("HONOR_ID"),
            honor_password=req("HONOR_PASSWORD"),
        )
```

- [ ] **Step 4: Написать `src/ihonor/__init__.py`** (пустой файл)

```python
```

- [ ] **Step 5: Написать failing-тест `tests/test_config.py`**

```python
import pytest
from ihonor.config import Config


def test_from_env_raises_when_missing(monkeypatch):
    for k in ("ICLOUD_APPLE_ID", "ICLOUD_PASSWORD", "HONOR_ID", "HONOR_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="ICLOUD_APPLE_ID"):
        Config.from_env()


def test_from_env_loads_all(monkeypatch):
    monkeypatch.setenv("ICLOUD_APPLE_ID", "a@b.com")
    monkeypatch.setenv("ICLOUD_PASSWORD", "pw")
    monkeypatch.setenv("HONOR_ID", "h")
    monkeypatch.setenv("HONOR_PASSWORD", "hp")
    cfg = Config.from_env()
    assert cfg.icloud_apple_id == "a@b.com"
    assert cfg.honor_id == "h"
```

- [ ] **Step 6: Установить и запустить тесты**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pytest -v`
Expected: оба теста PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example src tests
git commit -m "chore: scaffold spike project + config loader"
```

---

## Task 1: iCloud auth + персист сессии

**Files:**
- Create: `src/ihonor/icloud/__init__.py`, `src/ihonor/icloud/auth.py`

- [ ] **Step 1: Написать `src/ihonor/icloud/auth.py`**

`pyicloud` используем ТОЛЬКО для auth/сессии (его notes-поддержка мертва). Сессия и cookies оседают в `cookie_directory`, чтобы 2FA не запрашивался каждый раз.

```python
from pathlib import Path
from pyicloud import PyiCloudService


def login(apple_id: str, password: str, session_dir: str = ".icloud-session") -> PyiCloudService:
    Path(session_dir).mkdir(exist_ok=True)
    api = PyiCloudService(apple_id, password, cookie_directory=session_dir)
    if api.requires_2fa:
        code = input("2FA code: ").strip()
        if not api.validate_2fa_code(code):
            raise RuntimeError("iCloud 2FA validation failed")
        if not api.is_trusted_session:
            api.trust_session()
    return api
```

- [ ] **Step 2: Создать `src/ihonor/icloud/__init__.py`** (пустой)

```python
```

- [ ] **Step 3: Smoke — авторизоваться на реальном аккаунте**

Заполнить `.env` реальными iCloud-кредами. Запустить интерактивно:

Run: `python -c "from ihonor.config import Config; from ihonor.icloud.auth import login; c=Config.from_env(); api=login(c.icloud_apple_id, c.icloud_password); print('OK', api.account_name)"`
Expected: запрос 2FA (первый раз) → печатает `OK <имя>`. Папка `.icloud-session/` создана.

> Если auth/2FA не проходит headless — это первый красный флаг для гейта. Зафиксировать в VERDICT.

- [ ] **Step 4: Добавить `.icloud-session/` в .gitignore и commit**

```bash
echo ".icloud-session/" >> .gitignore
git add src/ihonor/icloud .gitignore
git commit -m "feat(icloud): auth + persisted session via pyicloud"
```

---

## Task 2: Вскрытие endpoints заметок iCloud

Заметки iCloud синхронизируются через **CloudKit Web Services** (`ckdatabasews`), контейнер `com.apple.notes`. Точные параметры запросов вскрываем перехватом web-клиента.

**Files:**
- Create: `docs/spike/icloud-findings.md`

- [ ] **Step 1: Запустить mitmproxy и перехватить трафик icloud.com/notes**

```bash
mitmweb --set confdir=~/.mitmproxy -w captures/icloud.flows
```
В браузере (с доверенным mitm-сертификатом) открыть https://www.icloud.com/notes/, выполнить вручную: открыть заметку, создать, отредактировать, удалить.

- [ ] **Step 2: Извлечь endpoints из дампа**

В mitmweb отфильтровать host `*ckdatabasews*` / `*icloud.com*`. Для каждой операции записать: URL, метод, заголовки auth (`X-Apple-*`, cookies), shape тела (record type, zone, fields).

- [ ] **Step 3: Заполнить `docs/spike/icloud-findings.md`**

Шаблон (заполнить реальными значениями из дампа):

```markdown
# iCloud Notes — вскрытые endpoints

## Auth
- Базовый хост ckdatabasews: <url>
- Нужные заголовки: <список>
- Источник cookies/токенов: <pyicloud session / dsid / ...>

## Операции (CloudKit records)
- LIST:   POST <url>/records/query  | recordType=<...> zone=<...>
- GET:    <...>
- CREATE: POST <url>/records/modify | operationType=create
- UPDATE: POST <url>/records/modify | operationType=update (+recordChangeTag)
- DELETE: POST <url>/records/modify | operationType=forceDelete

## Открытые вопросы / риски
- <...>
```

- [ ] **Step 4: Commit (без captures!)**

```bash
echo "captures/" >> .gitignore
git add docs/spike/icloud-findings.md .gitignore
git commit -m "docs(spike): icloud notes endpoints findings"
```

---

## Task 3: iCloud notes client — 5 операций + smoke

**Files:**
- Create: `src/ihonor/icloud/notes_client.py`, `scripts/icloud_smoke.py`

- [ ] **Step 1: Написать `src/ihonor/icloud/notes_client.py`**

Каркас по findings из Task 2. URL/тело подставить из `icloud-findings.md`. `<...>` ниже = заполнить реальными значениями.

```python
import httpx


class ICloudNotesClient:
    """Клиент заметок iCloud через ckdatabasews. Параметры — из docs/spike/icloud-findings.md."""

    def __init__(self, api):
        # api = PyiCloudService из auth.login(); берём из него сессию и базовый url ckdatabasews
        self._session = api.session
        self._base = api._get_webservice_url("ckdatabasews")  # уточнить имя в findings
        self._params = api.params

    def list_notes(self) -> list[dict]:
        r = self._session.post(
            f"{self._base}/database/1/com.apple.notes/production/private/records/query",
            params=self._params,
            json={"query": {"recordType": "<NoteRecordType>"}, "zoneID": {"zoneName": "<zone>"}},
        )
        r.raise_for_status()
        return r.json()["records"]

    def get_note(self, record_name: str) -> dict:
        r = self._session.post(
            f"{self._base}/database/1/com.apple.notes/production/private/records/lookup",
            params=self._params,
            json={"records": [{"recordName": record_name}], "zoneID": {"zoneName": "<zone>"}},
        )
        r.raise_for_status()
        return r.json()["records"][0]

    def create_note(self, title: str, body: str) -> str:
        r = self._session.post(
            f"{self._base}/database/1/com.apple.notes/production/private/records/modify",
            params=self._params,
            json={"operations": [{"operationType": "create", "record": {
                "recordType": "<NoteRecordType>",
                "fields": {"title": {"value": title}, "<bodyField>": {"value": body}},
            }}], "zoneID": {"zoneName": "<zone>"}},
        )
        r.raise_for_status()
        return r.json()["records"][0]["recordName"]

    def update_note(self, record_name: str, change_tag: str, title: str, body: str) -> None:
        r = self._session.post(
            f"{self._base}/database/1/com.apple.notes/production/private/records/modify",
            params=self._params,
            json={"operations": [{"operationType": "update", "record": {
                "recordName": record_name, "recordChangeTag": change_tag,
                "recordType": "<NoteRecordType>",
                "fields": {"title": {"value": title}, "<bodyField>": {"value": body}},
            }}], "zoneID": {"zoneName": "<zone>"}},
        )
        r.raise_for_status()

    def delete_note(self, record_name: str) -> None:
        r = self._session.post(
            f"{self._base}/database/1/com.apple.notes/production/private/records/modify",
            params=self._params,
            json={"operations": [{"operationType": "forceDelete",
                                  "record": {"recordName": record_name}}],
                  "zoneID": {"zoneName": "<zone>"}},
        )
        r.raise_for_status()
```

- [ ] **Step 2: Написать `scripts/icloud_smoke.py`**

```python
from ihonor.config import Config
from ihonor.icloud.auth import login
from ihonor.icloud.notes_client import ICloudNotesClient

cfg = Config.from_env()
api = login(cfg.icloud_apple_id, cfg.icloud_password)
client = ICloudNotesClient(api)

print("LIST before:", len(client.list_notes()))
rec = client.create_note("ihonor-spike", "hello from spike")
print("CREATED:", rec)
note = client.get_note(rec)
print("GET ok, changeTag:", note.get("recordChangeTag"))
client.update_note(rec, note["recordChangeTag"], "ihonor-spike", "edited")
print("UPDATED")
client.delete_note(rec)
print("DELETED")
print("LIST after:", len(client.list_notes()))
```

- [ ] **Step 3: Прогнать smoke против реального аккаунта**

Run: `python scripts/icloud_smoke.py`
Expected: печатает CREATED/GET/UPDATED/DELETED без исключений; LIST after == LIST before. Проверить в приложении Notes, что заметка появилась и исчезла.

> Любой шаг падает → зафиксировать точную ошибку в `icloud-findings.md` и в VERDICT. Это решает судьбу iCloud-стороны гейта.

- [ ] **Step 4: Commit**

```bash
git add src/ihonor/icloud/notes_client.py scripts/icloud_smoke.py
git commit -m "feat(icloud): notes client + smoke (5 ops)"
```

---

## Task 4: Перехват трафика HONOR (выбор канала)

HONOR Notes синхронизируется через HONOR Data Sync (HONOR ID). Web-notepad не подтверждён. Каналы-кандидаты: (a) трафик HONOR Notes Windows-клиента, (b) трафик приложения на телефоне. Спайк выбирает рабочий.

**Files:**
- Create: `docs/spike/honor-findings.md`

- [ ] **Step 1: Поднять mitmproxy как прокси**

```bash
mitmweb --set confdir=~/.mitmproxy -w captures/honor.flows
```

- [ ] **Step 2a: Канал A — Windows-клиент**

Установить HONOR Notes (Windows), направить системный прокси на mitmproxy, доверить сертификат. Создать/изменить/удалить заметку в клиенте, дать синхронизироваться.

- [ ] **Step 2b: Канал B — телефон (если A не даёт трафика заметок)**

Wi-Fi прокси телефона → mitmproxy, поставить mitm-сертификат как user CA. Открыть Notepad, синхронизировать. (Если включён certificate pinning — зафиксировать как блокер канала B.)

- [ ] **Step 3: Найти endpoints Data Sync для заметок**

В mitmweb отфильтровать host `*hihonor.com*` / `*cloud*`. Найти запросы с телом заметок. Записать: login/token-flow (HONOR ID), notes endpoints, формат записи, как помечаются изменения (cursor/version/mtime).

- [ ] **Step 4: Заполнить `docs/spike/honor-findings.md`**

```markdown
# HONOR Notes — вскрытые endpoints

## Рабочий канал
- [ ] A: Windows-клиент   [ ] B: телефон   — отметить рабочий

## Auth (HONOR ID)
- Login flow: <url(s)>, как получить токен/сессию
- Заголовки/токены для Data Sync: <...>

## Операции
- LIST/SYNC: <url, метод, тело, поле курсора>
- GET:       <...>
- CREATE:    <...>
- UPDATE:    <...> (как передаётся версия/etag)
- DELETE:    <...>

## Блокеры / риски
- pinning? обязателен ли клиент в петле? rate limits? <...>
```

- [ ] **Step 5: Commit**

```bash
git add docs/spike/honor-findings.md
git commit -m "docs(spike): honor data-sync endpoints findings"
```

---

## Task 5: HONOR notes client — 5 операций + smoke

**Files:**
- Create: `src/ihonor/honor/__init__.py`, `src/ihonor/honor/notes_client.py`, `scripts/honor_smoke.py`

- [ ] **Step 1: Создать `src/ihonor/honor/__init__.py`** (пустой)

```python
```

- [ ] **Step 2: Написать `src/ihonor/honor/notes_client.py`**

Каркас по findings из Task 4. Все `<...>` подставить из `honor-findings.md`. auth-flow зависит от вскрытого протокола — реализовать `_authenticate()` по findings.

```python
import httpx


class HonorNotesClient:
    """Клиент заметок HONOR Data Sync. Параметры — из docs/spike/honor-findings.md."""

    def __init__(self, honor_id: str, password: str):
        self._client = httpx.Client(timeout=30)
        self._token = self._authenticate(honor_id, password)

    def _authenticate(self, honor_id: str, password: str) -> str:
        # Реализовать по login-flow из findings (HONOR ID -> token).
        r = self._client.post("<login_url>", json={"account": honor_id, "password": password})
        r.raise_for_status()
        return r.json()["<token_field>"]

    def _headers(self) -> dict:
        return {"<auth_header>": self._token}

    def list_notes(self) -> list[dict]:
        r = self._client.post("<list_url>", headers=self._headers(), json={"<cursor_field>": None})
        r.raise_for_status()
        return r.json()["<records_field>"]

    def get_note(self, note_id: str) -> dict:
        r = self._client.post("<get_url>", headers=self._headers(), json={"id": note_id})
        r.raise_for_status()
        return r.json()

    def create_note(self, title: str, body: str) -> str:
        r = self._client.post("<create_url>", headers=self._headers(),
                              json={"title": title, "content": body})
        r.raise_for_status()
        return r.json()["<id_field>"]

    def update_note(self, note_id: str, version: str, title: str, body: str) -> None:
        r = self._client.post("<update_url>", headers=self._headers(),
                              json={"id": note_id, "version": version, "title": title, "content": body})
        r.raise_for_status()

    def delete_note(self, note_id: str) -> None:
        r = self._client.post("<delete_url>", headers=self._headers(), json={"id": note_id})
        r.raise_for_status()
```

- [ ] **Step 3: Написать `scripts/honor_smoke.py`**

```python
from ihonor.config import Config
from ihonor.honor.notes_client import HonorNotesClient

cfg = Config.from_env()
client = HonorNotesClient(cfg.honor_id, cfg.honor_password)

print("LIST before:", len(client.list_notes()))
nid = client.create_note("ihonor-spike", "hello from spike")
print("CREATED:", nid)
note = client.get_note(nid)
print("GET ok")
client.update_note(nid, note.get("version", ""), "ihonor-spike", "edited")
print("UPDATED")
client.delete_note(nid)
print("DELETED")
print("LIST after:", len(client.list_notes()))
```

- [ ] **Step 4: Прогнать smoke против реального HONOR-аккаунта**

Run: `python scripts/honor_smoke.py`
Expected: CREATED/GET/UPDATED/DELETED без исключений; заметка появляется/исчезает в Notepad на телефоне. Любой провал → точная ошибка в `honor-findings.md` и VERDICT.

- [ ] **Step 5: Commit**

```bash
git add src/ihonor/honor scripts/honor_smoke.py
git commit -m "feat(honor): notes client + smoke (5 ops)"
```

---

## Task 6: Вердикт гейта

**Files:**
- Create: `docs/spike/VERDICT.md`

- [ ] **Step 1: Заполнить `docs/spike/VERDICT.md`**

```markdown
# Phase 0 — вердикт гейта

Дата: <дата>

| Сторона | list | get | create | update | delete | headless? |
|---------|------|-----|--------|--------|---------|-----------|
| iCloud  |  ?   |  ?  |   ?    |   ?    |    ?    |    ?      |
| HONOR   |  ?   |  ?  |   ?    |   ?    |    ?    |    ?      |

## Итог
- [ ] ГЕЙТ ПРОЙДЕН — обе стороны дают все 5 операций headless → пишем план сборки движка.
- [ ] ГЕЙТ НЕ ПРОЙДЕН — сторона <...> провалила <...>.

## Если не пройден — пересмотр подхода
- iCloud упал → вариант Mac-in-loop (macnotesapp) или смена Apple-таргета.
- HONOR упал → требование Windows-клиента/телефона в петле, либо ручной экспорт.

## Ключевые риски на сборку
- Хрупкость reverse-API: <...>
- Стабильность ID для mapping: <...>
- Fidelity-потери: <...>
```

- [ ] **Step 2: Заполнить таблицу по факту smoke-прогонов (Task 3, Task 5)** и отметить итог.

- [ ] **Step 3: Commit**

```bash
git add docs/spike/VERDICT.md
git commit -m "docs(spike): phase 0 gate verdict"
```

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки §2 (спайк):** Task 1–6 покрывают доказательство 5 операций headless с обеих сторон + вердикт гейта. ✓
- **Out of scope (намеренно):** sync-engine, conflict-copy, state-store, scheduler, security at-rest — пишутся ВТОРЫМ планом ПОСЛЕ прохождения гейта (иначе плейсхолдеры по неизвестным endpoints).
- **Плейсхолдеры в коде:** `<...>` в Task 3/5 — НЕ плейсхолдеры плана, а явные слоты, заполняемые из findings-доков (Task 2/4), которые сам план обязывает создать первыми. Процедура их получения прописана пошагово.
- **Консистентность типов:** методы клиентов едины — `list_notes/get_note/create_note/update_note/delete_note` в обоих адаптерах и обоих smoke-скриптах. ✓
- **Безопасность:** `.env`, `.icloud-session/`, `captures/` — все в `.gitignore`; реальные креды/токены/дампы не коммитятся. ✓
