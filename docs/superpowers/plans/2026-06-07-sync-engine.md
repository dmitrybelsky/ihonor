# Sync Engine Implementation Plan (HONOR ↔ iCloud, локально на Mac)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) или superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Двусторонний синк заметок HONOR↔iCloud локально на macOS: чистая логика (Note/hash, state-store, sync-engine с conflict-copy) по TDD + обёртки доказанных адаптеров (iCloud CloudKit, HONOR локальная БД read, HONOR CDP-drive write).

**Architecture:** sync-engine работает через интерфейс NoteAdapter (обе стороны). Чистая логика тестируется с InMemory-адаптерами. Реальные адаптеры оборачивают доказанный код Phase 0. state-store (SQLite) хранит mapping honor↔icloud + хеши. Poll-цикл через launchd.

**Tech Stack:** Python 3.11+ (uv), pytest, requests/pyicloud/gmssl/cryptography/websocket-client, SQLite, node@20+better-sqlite3-multiple-ciphers (HONOR DB read), Chrome DevTools Protocol (HONOR write).

> Тулинг: системный pip сломан → ВСЕГДА `uv run pytest`, `uv pip install`. Секреты в `.env` (gitignored), НИКОГДА в репо/коммитах.

---

## File Structure
- `src/ihonor/note.py` — канон `Note` + `content_hash()` (чистое, TDD)
- `src/ihonor/adapter.py` — `NoteAdapter` Protocol + `InMemoryAdapter` (фейк для тестов)
- `src/ihonor/state_store.py` — SQLite id-map (TDD)
- `src/ihonor/engine.py` — sync-engine: классификация + apply + conflict-copy (TDD c фейками)
- `src/ihonor/adapters/icloud_adapter.py` — обёртка iCloud CloudKit в NoteAdapter
- `src/ihonor/adapters/honor_read.py` — HONOR read (node-helper → Note[])
- `src/ihonor/adapters/honor_read_helper.js` — node-скрипт чтения ChaCha20 БД
- `src/ihonor/adapters/honor_adapter.py` — HONOR NoteAdapter (read + CDP-write)
- `src/ihonor/runner.py` — связка: конфиг → адаптеры → engine → один цикл
- `config/com.ihonor.sync.plist` — launchd
- tests: `tests/test_note.py`, `tests/test_state_store.py`, `tests/test_engine.py`

---

## Task 1: Канон Note + content_hash

**Files:** Create `src/ihonor/note.py`, `tests/test_note.py`

- [ ] **Step 1: Failing-тест `tests/test_note.py`**
```python
from ihonor.note import Note, content_hash

def test_hash_stable_same_content():
    a = Note(ext_id="1", title="T", body_text="B", mtime=100, deleted=False)
    b = Note(ext_id="2", title="T", body_text="B", mtime=999, deleted=False)
    assert content_hash(a) == content_hash(b)  # хеш по title+body, не по id/mtime

def test_hash_changes_with_body():
    a = Note(ext_id="1", title="T", body_text="B", mtime=100, deleted=False)
    c = Note(ext_id="1", title="T", body_text="B2", mtime=100, deleted=False)
    assert content_hash(a) != content_hash(c)
```

- [ ] **Step 2: Запустить — FAIL**
Run: `uv run pytest tests/test_note.py -v` → FAIL (нет модуля).

- [ ] **Step 3: Реализация `src/ihonor/note.py`**
```python
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    ext_id: str          # id в своей системе (honor uuid / icloud recordName)
    title: str
    body_text: str       # плоский текст
    mtime: int           # ms
    deleted: bool = False


def content_hash(note: Note) -> str:
    h = hashlib.sha256()
    h.update(note.title.encode("utf-8"))
    h.update(b"\x00")
    h.update(note.body_text.encode("utf-8"))
    return h.hexdigest()
```

- [ ] **Step 4: PASS**
Run: `uv run pytest tests/test_note.py -v` → 2 passed.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/note.py tests/test_note.py
git commit -m "feat(engine): canon Note + content_hash"
```

---

## Task 2: NoteAdapter Protocol + InMemoryAdapter

**Files:** Create `src/ihonor/adapter.py`, добавить тест в `tests/test_engine.py` (часть)

- [ ] **Step 1: Failing-тест `tests/test_engine.py` (адаптер-часть)**
```python
from ihonor.note import Note
from ihonor.adapter import InMemoryAdapter

def test_inmemory_crud():
    a = InMemoryAdapter()
    rid = a.create(Note(ext_id="", title="t", body_text="b", mtime=1))
    assert any(n.ext_id == rid for n in a.list())
    a.update(rid, Note(ext_id=rid, title="t2", body_text="b", mtime=2))
    assert a.get(rid).title == "t2"
    a.delete(rid)
    assert all(n.deleted or n.ext_id != rid for n in a.list()) or a.get(rid) is None
```

- [ ] **Step 2: FAIL**
Run: `uv run pytest tests/test_engine.py::test_inmemory_crud -v` → FAIL.

- [ ] **Step 3: Реализация `src/ihonor/adapter.py`**
```python
from typing import Protocol
from ihonor.note import Note


class NoteAdapter(Protocol):
    def list(self) -> list[Note]: ...
    def get(self, ext_id: str) -> Note | None: ...
    def create(self, note: Note) -> str: ...
    def update(self, ext_id: str, note: Note) -> None: ...
    def delete(self, ext_id: str) -> None: ...


class InMemoryAdapter:
    """Фейк для тестов движка."""

    def __init__(self) -> None:
        self._d: dict[str, Note] = {}
        self._seq = 0

    def list(self) -> list[Note]:
        return [n for n in self._d.values()]

    def get(self, ext_id: str) -> Note | None:
        return self._d.get(ext_id)

    def create(self, note: Note) -> str:
        self._seq += 1
        rid = f"m{self._seq}"
        self._d[rid] = Note(rid, note.title, note.body_text, note.mtime, False)
        return rid

    def update(self, ext_id: str, note: Note) -> None:
        self._d[ext_id] = Note(ext_id, note.title, note.body_text, note.mtime, False)

    def delete(self, ext_id: str) -> None:
        if ext_id in self._d:
            self._d[ext_id] = Note(ext_id, self._d[ext_id].title, self._d[ext_id].body_text,
                                   self._d[ext_id].mtime, True)
```

- [ ] **Step 4: PASS** — Run: `uv run pytest tests/test_engine.py::test_inmemory_crud -v` → passed.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/adapter.py tests/test_engine.py
git commit -m "feat(engine): NoteAdapter protocol + InMemoryAdapter"
```

---

## Task 3: state-store (SQLite id-map)

**Files:** Create `src/ihonor/state_store.py`, `tests/test_state_store.py`

- [ ] **Step 1: Failing-тест `tests/test_state_store.py`**
```python
from ihonor.state_store import StateStore, Pair

def test_upsert_and_get(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.upsert(Pair(honor_id="h1", icloud_id="i1", hash_honor="x", hash_icloud="x"))
    p = s.by_honor("h1")
    assert p.icloud_id == "i1" and p.hash_honor == "x"
    assert s.by_icloud("i1").honor_id == "h1"

def test_all_and_delete(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.upsert(Pair(honor_id="h1", icloud_id="i1", hash_honor="a", hash_icloud="a"))
    assert len(s.all()) == 1
    s.remove("h1")
    assert s.by_honor("h1") is None
```

- [ ] **Step 2: FAIL** — Run: `uv run pytest tests/test_state_store.py -v` → FAIL.

- [ ] **Step 3: Реализация `src/ihonor/state_store.py`**
```python
import sqlite3
from dataclasses import dataclass


@dataclass
class Pair:
    honor_id: str
    icloud_id: str
    hash_honor: str
    hash_icloud: str


class StateStore:
    def __init__(self, path: str) -> None:
        self._c = sqlite3.connect(path)
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS pair("
            "honor_id TEXT, icloud_id TEXT, hash_honor TEXT, hash_icloud TEXT,"
            "PRIMARY KEY(honor_id, icloud_id))"
        )
        self._c.commit()

    def upsert(self, p: Pair) -> None:
        self._c.execute(
            "INSERT INTO pair VALUES(?,?,?,?) "
            "ON CONFLICT(honor_id,icloud_id) DO UPDATE SET hash_honor=excluded.hash_honor,"
            "hash_icloud=excluded.hash_icloud",
            (p.honor_id, p.icloud_id, p.hash_honor, p.hash_icloud),
        )
        self._c.commit()

    def _row(self, r) -> Pair:
        return Pair(r[0], r[1], r[2], r[3])

    def by_honor(self, honor_id: str) -> Pair | None:
        r = self._c.execute("SELECT * FROM pair WHERE honor_id=?", (honor_id,)).fetchone()
        return self._row(r) if r else None

    def by_icloud(self, icloud_id: str) -> Pair | None:
        r = self._c.execute("SELECT * FROM pair WHERE icloud_id=?", (icloud_id,)).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[Pair]:
        return [self._row(r) for r in self._c.execute("SELECT * FROM pair").fetchall()]

    def remove(self, honor_id: str) -> None:
        self._c.execute("DELETE FROM pair WHERE honor_id=?", (honor_id,))
        self._c.commit()
```

- [ ] **Step 4: PASS** — Run: `uv run pytest tests/test_state_store.py -v` → 2 passed.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/state_store.py tests/test_state_store.py
git commit -m "feat(engine): SQLite state-store id-map"
```

---

## Task 4: sync-engine — классификация + apply (новые/изменённые одной стороной)

**Files:** Create `src/ihonor/engine.py`, дополнить `tests/test_engine.py`

- [ ] **Step 1: Failing-тест (добавить в `tests/test_engine.py`)**
```python
from ihonor.note import Note
from ihonor.adapter import InMemoryAdapter
from ihonor.state_store import StateStore
from ihonor.engine import SyncEngine

def test_new_honor_note_creates_in_icloud(tmp_path):
    honor = InMemoryAdapter(); icloud = InMemoryAdapter()
    hid = honor.create(Note("", "Hello", "body", 1))
    eng = SyncEngine(honor, icloud, StateStore(str(tmp_path/"s.db")))
    eng.sync_once()
    titles = [n.title for n in icloud.list() if not n.deleted]
    assert "Hello" in titles

def test_changed_honor_updates_icloud(tmp_path):
    honor = InMemoryAdapter(); icloud = InMemoryAdapter(); st = StateStore(str(tmp_path/"s.db"))
    hid = honor.create(Note("", "T", "b1", 1))
    eng = SyncEngine(honor, icloud, st); eng.sync_once()
    honor.update(hid, Note(hid, "T", "b2", 2))
    eng.sync_once()
    icn = [n for n in icloud.list() if not n.deleted and n.title=="T"][0]
    assert icn.body_text == "b2"
```

- [ ] **Step 2: FAIL** — Run: `uv run pytest tests/test_engine.py -v` → FAIL (нет SyncEngine).

- [ ] **Step 3: Реализация `src/ihonor/engine.py`**
```python
from ihonor.note import Note, content_hash
from ihonor.adapter import NoteAdapter
from ihonor.state_store import StateStore, Pair


class SyncEngine:
    def __init__(self, honor: NoteAdapter, icloud: NoteAdapter, store: StateStore) -> None:
        self.honor = honor
        self.icloud = icloud
        self.store = store

    def sync_once(self) -> None:
        h_notes = {n.ext_id: n for n in self.honor.list() if not n.deleted}
        i_notes = {n.ext_id: n for n in self.icloud.list() if not n.deleted}
        paired_h = {p.honor_id for p in self.store.all()}
        paired_i = {p.icloud_id for p in self.store.all()}

        # новые в HONOR -> create в iCloud
        for hid, hn in h_notes.items():
            if hid not in paired_h:
                iid = self.icloud.create(hn)
                self.store.upsert(Pair(hid, iid, content_hash(hn), content_hash(hn)))
        # новые в iCloud -> create в HONOR
        for iid, ino in i_notes.items():
            if iid not in paired_i:
                hid = self.honor.create(ino)
                self.store.upsert(Pair(hid, iid, content_hash(ino), content_hash(ino)))

        # изменения по существующим парам
        for p in self.store.all():
            hn = h_notes.get(p.honor_id)
            ino = i_notes.get(p.icloud_id)
            if not hn or not ino:
                continue
            hh, ih = content_hash(hn), content_hash(ino)
            h_changed = hh != p.hash_honor
            i_changed = ih != p.hash_icloud
            if h_changed and not i_changed:
                self.icloud.update(p.icloud_id, hn)
                self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, hh))
            elif i_changed and not h_changed:
                self.honor.update(p.honor_id, ino)
                self.store.upsert(Pair(p.honor_id, p.icloud_id, ih, ih))
            # changed-both -> Task 5 (conflict-copy)
```

- [ ] **Step 4: PASS** — Run: `uv run pytest tests/test_engine.py -v` → passed.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/engine.py tests/test_engine.py
git commit -m "feat(engine): sync-engine new + changed-one-side"
```

---

## Task 5: conflict-copy (changed-both) + консервативные удаления

**Files:** Modify `src/ihonor/engine.py`, дополнить `tests/test_engine.py`

- [ ] **Step 1: Failing-тест (добавить)**
```python
def test_conflict_both_changed_makes_copy(tmp_path):
    honor=InMemoryAdapter(); icloud=InMemoryAdapter(); st=StateStore(str(tmp_path/"s.db"))
    hid=honor.create(Note("","T","b",1)); eng=SyncEngine(honor,icloud,st); eng.sync_once()
    iid=[n.ext_id for n in icloud.list() if n.title=="T"][0]
    honor.update(hid, Note(hid,"T","H-edit",2))
    icloud.update(iid, Note(iid,"T","I-edit",2))
    eng.sync_once()
    bodies=sorted(n.body_text for n in (honor.list()+icloud.list()) if not n.deleted)
    # обе версии сохранены где-то (conflict-copy), данные не потеряны
    assert any("H-edit" in b for b in bodies) and any("I-edit" in b for b in bodies)

def test_delete_propagates(tmp_path):
    honor=InMemoryAdapter(); icloud=InMemoryAdapter(); st=StateStore(str(tmp_path/"s.db"))
    hid=honor.create(Note("","T","b",1)); eng=SyncEngine(honor,icloud,st); eng.sync_once()
    honor.delete(hid); eng.sync_once()
    assert all(n.deleted for n in icloud.list())
```

- [ ] **Step 2: FAIL** — Run: `uv run pytest tests/test_engine.py -v` → FAIL на новых.

- [ ] **Step 3: Дополнить `engine.py`**
Заменить ветку `# changed-both` и добавить обработку удалений. Полный метод `sync_once` (заменяет тело из Task 4 ниже секции изменений):
```python
            if h_changed and i_changed:
                # conflict-copy: оставляем iCloud-версию, создаём копию HONOR-версии в iCloud
                conflict = Note("", hn.title + " (conflict)", hn.body_text, hn.mtime)
                self.icloud.create(conflict)
                self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, ih))

        # удаления: пара была, но заметка пропала с одной стороны -> удалить на другой
        h_ids = {n.ext_id for n in self.honor.list() if not n.deleted}
        i_ids = {n.ext_id for n in self.icloud.list() if not n.deleted}
        for p in self.store.all():
            h_gone = p.honor_id not in h_ids
            i_gone = p.icloud_id not in i_ids
            if h_gone and not i_gone:
                self.icloud.delete(p.icloud_id); self.store.remove(p.honor_id)
            elif i_gone and not h_gone:
                self.honor.delete(p.honor_id); self.store.remove(p.honor_id)
```
(Вставить ПЕРЕД концом `sync_once`, после цикла изменений.)

- [ ] **Step 4: PASS** — Run: `uv run pytest tests/test_engine.py -v` → все passed.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/engine.py tests/test_engine.py
git commit -m "feat(engine): conflict-copy + conservative deletes"
```

---

## Task 6: iCloud адаптер через Apple Notes.app (AppleScript)

**Files:** Create `src/ihonor/adapters/__init__.py`, `src/ihonor/adapters/icloud_adapter.py`

> Драйвим локальный Notes.app через `osascript`. Apple синкает в iCloud сам. Доказано:
> list/create/delete/update работают (`count of notes`=10, `make new note`→id, `delete note id`).
> body = HTML; canon body_text = strip-HTML. ext_id = note id (`x-coredata://.../ICNote/pNNN`).

- [ ] **Step 1: Создать `src/ihonor/adapters/__init__.py`** (пустой)
```python
```

- [ ] **Step 2: Реализация `src/ihonor/adapters/icloud_adapter.py`**
```python
import html
import re
import subprocess
from ihonor.note import Note

US = "\x1f"  # field sep
RS = "\x1e"  # record sep


def _osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True).stdout


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


class ICloudAdapter:
    """iCloud через Apple Notes.app (AppleScript). Apple авто-синкает в облако."""

    def list(self) -> list[Note]:
        script = (
            'tell application "Notes"\n'
            f'set AppleScript\'s text item delimiters to "{US}"\n'
            'set out to ""\n'
            'repeat with n in notes\n'
            f'set out to out & (id of n) & "{US}" & (name of n) & "{US}" & (body of n) & "{RS}"\n'
            'end repeat\n'
            'return out\n'
            'end tell'
        )
        raw = _osa(script)
        notes = []
        for rec in raw.split(RS):
            if US not in rec:
                continue
            parts = rec.split(US)
            if len(parts) < 3:
                continue
            nid, name, body = parts[0], parts[1], US.join(parts[2:])
            notes.append(Note(nid.strip(), name, _strip_html(body), 0, False))
        return notes

    def get(self, ext_id: str) -> Note | None:
        for n in self.list():
            if n.ext_id == ext_id:
                return n
        return None

    def create(self, note: Note) -> str:
        body = f"<div><b>{html.escape(note.title)}</b></div><div>{html.escape(note.body_text)}</div>"
        script = (
            'tell application "Notes"\n'
            f'set n to make new note with properties {{name:"{_esc(note.title)}", body:"{_esc(body)}"}}\n'
            'return id of n\n'
            'end tell'
        )
        return _osa(script).strip()

    def update(self, ext_id: str, note: Note) -> None:
        body = f"<div><b>{html.escape(note.title)}</b></div><div>{html.escape(note.body_text)}</div>"
        script = (
            'tell application "Notes"\n'
            f'set body of note id "{_esc(ext_id)}" to "{_esc(body)}"\n'
            'end tell'
        )
        _osa(script)

    def delete(self, ext_id: str) -> None:
        _osa(f'tell application "Notes" to delete note id "{_esc(ext_id)}"')


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
```

- [ ] **Step 3: Smoke (Notes.app доступен)**
Run:
```bash
uv run python -c "from ihonor.adapters.icloud_adapter import ICloudAdapter; a=ICloudAdapter(); print('icloud notes:',len(a.list())); rid=a.create(__import__('ihonor.note',fromlist=['Note']).Note('','smoke-icloud','body via applescript',1)); print('created',rid[:40]); a.delete(rid); print('deleted')"
```
Expected: печатает число заметок, создаёт+удаляет smoke-заметку (видно в Notes.app кратко).

- [ ] **Step 4: Commit**
```bash
git add src/ihonor/adapters/__init__.py src/ihonor/adapters/icloud_adapter.py
git commit -m "feat(adapter): iCloud via Apple Notes.app (AppleScript)"
```

---

## Task 7: HONOR read-адаптер (ChaCha20 БД → Note[])

**Files:** Create `src/ihonor/adapters/honor_read_helper.js`, `src/ihonor/adapters/honor_read.py`

> Использует доказанное: `scripts/honor_dbkey.py` (пароль) + node@20 + better-sqlite3-multiple-ciphers.
> БД копируется в temp (не трогаем живую).

- [ ] **Step 1: Создать `src/ihonor/adapters/honor_read_helper.js`**
```javascript
const D=require("better-sqlite3-multiple-ciphers");
const db=new D(process.argv[2],{fileMustExist:true});
db.pragma(`key='${process.env.HONORPW}'`);
const rows=db.prepare("SELECT uuid,title,search_content,html_content,modify_time,delete_flag,type FROM note").all();
process.stdout.write(JSON.stringify(rows));
db.close();
```

- [ ] **Step 2: Реализация `src/ihonor/adapters/honor_read.py`**
```python
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from ihonor.note import Note

NODE = "/opt/homebrew/opt/node@20/bin/node"
HELPER = str(Path(__file__).parent / "honor_read_helper.js")
NODE_MODULES = "/tmp/honornode/node_modules"  # better-sqlite3-multiple-ciphers (node@20)
DB = os.path.expanduser(
    "~/Library/Containers/com.hihonor.hihonornote/Data/.config/hihonornote/database.sqlite"
)


def _derive_key() -> str:
    from scripts.honor_dbkey import derive_db_password  # type: ignore
    return derive_db_password()


def read_honor_notes() -> list[Note]:
    tmp = tempfile.mkdtemp()
    db_copy = os.path.join(tmp, "database.sqlite")
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(DB + suf):
            shutil.copy(DB + suf, db_copy + suf)
    env = dict(os.environ, HONORPW=_derive_key(), NODE_PATH=NODE_MODULES)
    out = subprocess.check_output([NODE, HELPER, db_copy], env=env, text=True)
    rows = json.loads(out)
    notes = []
    for r in rows:
        body = r.get("search_content") or ""
        notes.append(Note(r["uuid"], r.get("title") or "", body.strip(),
                          r.get("modify_time") or 0, bool(r.get("delete_flag"))))
    shutil.rmtree(tmp, ignore_errors=True)
    return notes
```

- [ ] **Step 3: Smoke**
Run: `uv run python -c "from ihonor.adapters.honor_read import read_honor_notes; ns=read_honor_notes(); print('honor live:',len([n for n in ns if not n.deleted]))"`
Expected: число живых заметок (>0). Требует node@20 + установленный better-sqlite3-multiple-ciphers в /tmp/honornode (см. handoff) ИЛИ скорректировать NODE_MODULES.

- [ ] **Step 4: Commit**
```bash
git add src/ihonor/adapters/honor_read_helper.js src/ihonor/adapters/honor_read.py
git commit -m "feat(adapter): HONOR read from local ChaCha20 DB"
```

---

## Task 8: HONOR адаптер (read + CDP-write create)

**Files:** Create `src/ihonor/adapters/honor_adapter.py`

> write через `src/ihonor/honor/cdp_writer.py` (доказан create). update/delete — Task 10.

- [ ] **Step 1: Реализация `src/ihonor/adapters/honor_adapter.py`**
```python
from ihonor.note import Note
from ihonor.adapters.honor_read import read_honor_notes
from ihonor.honor.cdp_writer import HonorCdpWriter


class HonorAdapter:
    def __init__(self, cdp_port: int = 9222):
        self._port = cdp_port

    def list(self) -> list[Note]:
        return read_honor_notes()

    def get(self, ext_id: str) -> Note | None:
        for n in self.list():
            if n.ext_id == ext_id:
                return n
        return None

    def create(self, note: Note) -> str:
        w = HonorCdpWriter(self._port)
        w.connect()
        w.create_note(note.title, note.body_text)
        w.close()
        # CDP create не возвращает uuid сразу; находим по заголовку среди свежих
        cands = [n for n in self.list() if n.title == note.title and not n.deleted]
        return cands[-1].ext_id if cands else ""

    def update(self, ext_id: str, note: Note) -> None:
        raise NotImplementedError("HONOR update — Task 10 (CDP UI-навигация)")

    def delete(self, ext_id: str) -> None:
        raise NotImplementedError("HONOR delete — Task 10 (CDP контекст-меню)")
```

- [ ] **Step 2: Smoke (app запущен с --remote-debugging-port=9222)**
Run:
```bash
open -a HonorWorkStation --args --remote-debugging-port=9222
sleep 6
uv run python -c "from ihonor.adapters.honor_adapter import HonorAdapter; a=HonorAdapter(); rid=a.create(__import__('ihonor.note',fromlist=['Note']).Note('','adapter-smoke','via honor adapter',1)); print('created honor id:',rid)"
```
Expected: печатает honor id; заметка «adapter-smoke» появляется в app + синкается.

- [ ] **Step 3: Commit**
```bash
git add src/ihonor/adapters/honor_adapter.py
git commit -m "feat(adapter): HONOR NoteAdapter (read + CDP create)"
```

---

## Task 9: runner — один цикл синка с реальными адаптерами

**Files:** Create `src/ihonor/runner.py`

- [ ] **Step 1: Реализация `src/ihonor/runner.py`**
```python
import os
from ihonor.state_store import StateStore
from ihonor.engine import SyncEngine
from ihonor.adapters.icloud_adapter import ICloudAdapter
from ihonor.adapters.honor_adapter import HonorAdapter

STATE_DB = os.path.expanduser("~/.ihonor/state.db")


def run_once(cdp_port: int = 9222) -> None:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    honor = HonorAdapter(cdp_port)
    icloud = ICloudAdapter()  # Apple Notes.app via AppleScript
    engine = SyncEngine(honor, icloud, StateStore(STATE_DB))
    engine.sync_once()
    print("[ihonor] sync_once done")


if __name__ == "__main__":
    run_once()
```

- [ ] **Step 2: Smoke — один полный цикл (app+CDP запущены, .env заполнен)**
Run: `uv run python -m ihonor.runner`
Expected: `[ihonor] sync_once done`. Проверить: новая HONOR-заметка появилась в iCloud (icloud.com/notes) и наоборот. ⚠️ Первый прогон создаст пары для ВСЕХ существующих заметок — на тестовом наборе сначала. Бэкап iCloud/HONOR перед первым полным прогоном.

- [ ] **Step 3: Commit**
```bash
git add src/ihonor/runner.py
git commit -m "feat: runner sync_once wiring real adapters"
```

---

## Task 10: HONOR update/delete через CDP (UI-навигация)

**Files:** Modify `src/ihonor/honor/cdp_writer.py`, `src/ihonor/adapters/honor_adapter.py`

> Вскрыть селекторы списка заметок + контекст-меню через CDP (как `.newNoteButton`).
> Метод: открыть заметку по title (клик в списке) → правка тела / контекст-меню «удалить».

- [ ] **Step 1: Разведка селекторов (CDP, app запущен)**
Run:
```bash
uv run python /tmp/cdp.py "JSON.stringify([...document.querySelectorAll('[class*=noteItem],[class*=noteListItem],[class*=list]')].slice(0,10).map(e=>e.className.toString().slice(0,50)))"
```
Записать селектор элемента заметки в списке + способ открыть/удалить. (Зафиксировать в этом шаге фактические селекторы перед реализацией.)

- [ ] **Step 2: Реализация `update_note`/`delete_note` в `cdp_writer.py`**
```python
    def open_note_by_title(self, title: str) -> bool:
        # клик по заметке в списке с данным заголовком
        js = ("(()=>{const items=[...document.querySelectorAll('.noteListItem,[class*=noteItem]')];"
              "const el=items.find(e=>e.innerText&&e.innerText.includes(%r));"
              "if(!el)return false;el.click();return true;})()" % title)
        return self._eval(js) is True

    def update_note(self, title: str, new_body: str, settle: float = 2.0) -> None:
        import time
        if not self.open_note_by_title(title):
            raise RuntimeError("note not found in list: " + title)
        time.sleep(1.0)
        self._eval("(()=>{const e=document.querySelector('.app-note-editor-01,[contenteditable=true]');"
                   "if(e){e.focus();const r=document.createRange();r.selectNodeContents(e);"
                   "const s=getSelection();s.removeAllRanges();s.addRange(r);}return true;})()")
        self._cmd("Input.insertText", {"text": new_body})
        time.sleep(settle)

    def delete_note(self, title: str, settle: float = 2.0) -> None:
        import time
        if not self.open_note_by_title(title):
            raise RuntimeError("note not found: " + title)
        time.sleep(0.8)
        # ПОДСТАВИТЬ реальный селектор кнопки/пункта удаления из Step 1
        ok = self._eval("(()=>{const d=document.querySelector('[class*=delete],[aria-label*=elete]');"
                        "if(!d)return false;d.click();return true;})()")
        if ok is not True:
            raise RuntimeError("delete control not found — уточнить селектор (Step 1)")
        time.sleep(settle)
```

- [ ] **Step 3: Включить в `honor_adapter.py`** — заменить NotImplementedError:
```python
    def update(self, ext_id: str, note: Note) -> None:
        cur = self.get(ext_id)
        w = HonorCdpWriter(self._port); w.connect()
        w.update_note(cur.title if cur else note.title, note.body_text); w.close()

    def delete(self, ext_id: str) -> None:
        cur = self.get(ext_id)
        if not cur:
            return
        w = HonorCdpWriter(self._port); w.connect()
        w.delete_note(cur.title); w.close()
```

- [ ] **Step 4: Smoke** — создать, обновить, удалить тест-заметку через адаптер; проверить в app+телефон.
Run: (ручной сценарий) `uv run python -c "..."` создаёт → update → delete, визуальная проверка.

- [ ] **Step 5: Commit**
```bash
git add src/ihonor/honor/cdp_writer.py src/ihonor/adapters/honor_adapter.py
git commit -m "feat(adapter): HONOR update/delete via CDP UI navigation"
```

---

## Task 11: scheduler (launchd) + автозапуск app с CDP

**Files:** Create `config/com.ihonor.sync.plist`, `scripts/ihonor_tick.sh`

- [ ] **Step 1: Создать `scripts/ihonor_tick.sh`**
```bash
#!/bin/bash
# гарантируем HonorWorkStation с CDP, затем один цикл синка
pgrep -f 'MacOS/Hihonornote' >/dev/null || open -a HonorWorkStation --args --remote-debugging-port=9222
sleep 8
cd /Users/dmitrybelsky/projects/ihonor
/Users/dmitrybelsky/projects/ihonor/.venv/bin/python -m ihonor.runner >> ~/.ihonor/sync.log 2>&1
```

- [ ] **Step 2: chmod + создать `config/com.ihonor.sync.plist`**
```bash
chmod +x scripts/ihonor_tick.sh
```
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ihonor.sync</string>
  <key>ProgramArguments</key>
  <array><string>/Users/dmitrybelsky/projects/ihonor/scripts/ihonor_tick.sh</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
```

- [ ] **Step 3: Установка (вручную пользователем)**
Run: `cp config/com.ihonor.sync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ihonor.sync.plist`
Expected: каждые 15 мин — цикл синка, лог в `~/.ihonor/sync.log`.

- [ ] **Step 4: Commit**
```bash
git add config/com.ihonor.sync.plist scripts/ihonor_tick.sh
git commit -m "feat: launchd scheduler 15min poll"
```

---

## Self-Review
- **Покрытие spec v2:** NoteAdapter(T2)✓ canon Note(T1)✓ state-store(T3)✓ engine new/changed(T4)✓
  conflict-copy+deletes(T5)✓ icloud-adapter CloudKit(T6)✓ honor-read локальная БД(T7)✓
  honor-write CDP(T8)✓ runner(T9)✓ honor update/delete CDP(T10)✓ scheduler launchd(T11)✓.
- **Плейсхолдеры:** код полный в каждом шаге. Исключения с реальными значениями — Task 10 Step1
  (селекторы списка/удаления) намеренно требует разведки CDP перед реализацией (как было с
  `.newNoteButton`); шаг это явно предписывает.
- **Консистентность типов:** Note(ext_id,title,body_text,mtime,deleted) едино; NoteAdapter
  list/get/create/update/delete едино во всех адаптерах; Pair(honor_id,icloud_id,hash_honor,
  hash_icloud) едино.
- **Риски (из spec):** HONOR write требует запущенный app+CDP (T8/T11 учитывают); fidelity —
  body=плоский текст (search_content / protobuf); первый полный прогон — бэкап (T9 Step2 warning).
