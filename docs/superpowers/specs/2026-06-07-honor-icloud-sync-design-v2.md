# Дизайн v2: двусторонняя синхронизация HONOR ↔ iCloud (локально на Mac)

Дата: 2026-06-07. Статус: утверждён (после Phase 0 спайка).
Заменяет v1 (2026-06-06): «headless cloud server + reverse private API» → реальные механизмы,
**запуск локально на Mac пользователя**.

## Цель
Двусторонняя синхронизация заметок HONOR ↔ iCloud, **локально на macOS**. Текстовые заметки
(type=2) — основной объём. Рукопись/вложения — best-effort/скип (см. fidelity).

## Среда исполнения
- macOS пользователя. Зависимости: **запущенный залогиненный HonorWorkStation** (для HONOR
  write через CDP + он же держит локальную БД для read), доступ к iCloud (Apple ID + 2FA один раз).
- Питон-процесс (launchd) опрашивает обе стороны по интервалу.

## Реальные механизмы (вскрыты Phase 0, всё доказано)
### iCloud через Apple Notes.app (AppleScript) — ОСНОВНОЙ путь (локально на Mac, ✅)
- Драйвим локальный **Notes.app по AppleScript** (`osascript`). Apple сам синкает в iCloud-облако
  (симметрично HONOR: драйвим родной app). Официально, стабильно, без 2FA-токенов и ADP-проблем.
- CRUD доказан: `count of notes`=10 (= те же что в облаке), `make new note {name,body}` → id
  (`x-coredata://.../ICNote/pNNN`), `delete note id`, `set body of note id`. ✅
- body = HTML; canon body_text = strip-HTML. ext_id = note id (стабильный). 
- АЛЬТЕРНАТИВА (если без Notes.app / headless-сервер): reverse-CloudKit `ckdatabasews`
  (вскрыто Phase 0: changes/zone + records/modify, protobuf/gzip) — `src/ihonor/icloud/*`,
  `scripts/icloud_*`. Хрупче; для local-Mac не нужен.

### HONOR READ (локальная БД, ✅)
- `~/Library/Containers/com.hihonor.hihonornote/Data/.config/hihonornote/database.sqlite`,
  шифр ChaCha20 (better-sqlite3-multiple-ciphers). Ключ: `scripts/honor_dbkey.py` (ctypes →
  нативная `honorcloud_aead_decrypt`). Чтение: node@20 + better-sqlite3-multiple-ciphers.
- Поля note: uuid, title, html_content, search_content, dirty, guid, folder_uuid, delete_flag,
  modify_time, type(2=text/6=handwrite).

### HONOR WRITE (CDP-drive app, ✅ ПОЛНЫЙ: create+update+delete)
- Внешний прямой write в облако заблокирован (device-enrollment + token-binding + DB-integrity).
- Решение: драйв HonorWorkStation → app пишет родным путём (своя крипта SM2/AES-GCM + upload)
  → синк в облако/телефон. `src/ihonor/honor/cdp_writer.py`. Запуск app:
  `open -a HonorWorkStation --args --remote-debugging-port=9222`.
- **create**: click newNoteButton → React-set title (textarea.noteTitleText, native setter+input
  event) → center-click body (.app-note-editor-01) + Input.insertText → blur. title+body, синк ✅.
- **update**: open card → click-center body → DOM selectNodeContents (select-all, подтвердить
  непустым) → реальный Input.insertText (Slate beforeinput заменяет) → blur. Чистая замена ✅.
- **delete**: реальные OS-клики **cliclick** (CDP-синтетика/AX не триггерят): activate →
  cliclick rc по карточке (контекст-меню) → cliclick по Delete → cliclick по confirm-Delete.
  Координаты: screen = window.screenX/Y + viewport (frameless). Надёжно ✅.
- ЗАВИСИМОСТЬ: `cliclick` (brew install cliclick) + Accessibility (для cliclick OS-кликов).

## Архитектура движка
```
            ┌──────────────── sync-engine ────────────────┐
            │  poll → classify → apply → conflict-copy     │
            └───▲────────────────────────────────────▲─────┘
       NoteAdapter API                          NoteAdapter API
   ┌────────┴─────────┐                   ┌───────────┴──────────┐
   │  icloud-adapter  │                   │   honor-adapter      │
   │  (CloudKit RW)   │                   │ read: local DB       │
   │                  │                   │ write: CDP-drive app │
   └────────┬─────────┘                   └───────────┬──────────┘
            │                                          │
       ┌────┴──────────── state-store (SQLite) ────────┴────┐
       │ map: honor_uuid ↔ icloud_recordName ↔ hash/mtime    │
       └─────────────────────────▲──────────────────────────┘
                           ┌──────┴──────┐
                           │  scheduler  │ launchd, poll interval
                           └─────────────┘
```

### NoteAdapter (обе стороны)
`list() -> [Note]`, `get(id)`, `create(Note)->id`, `update(id,Note)`, `delete(id)`.
Канон: `Note{ext_id, title, body_text, mtime, hash, deleted}`. body_text = плоский текст
(iCloud: из protobuf; HONOR: search_content/html→text). Богатый html — фаза 2.

### state-store (SQLite)
Строка пары: `{honor_uuid, honor_guid, icloud_record, last_hash_honor, last_hash_icloud,
last_synced_at, tombstone}`. Хеш по канону (title+body) для детекта изменений.

### sync-engine
- Каждый poll: list() обе стороны → классификация по mapping: new / changed-one / changed-both /
  deleted-one.
- changed-one → apply на другую (create/update).
- **changed-both → conflict-copy** (обе версии, одну тег `(conflict YYYY-MM-DD)`). Cross-system
  mtime недостоверны → не last-writer-wins.
- deleted-one → propagate delete (только если был в mapping И подтверждённо исчез).
- HONOR write через CDP требует запущенный app; если не запущен — очередь, ретрай.

## Fidelity (дефолт)
Текст + заголовок. Рукопись (type=6)/вложения/чек-листы — скип с логом (фаза 2). iCloud body —
плоский текст (protobuf без rich-форматирования на запись).

## Риски
- HONOR write зависит от запущенного HonorWorkStation + CDP (хрупко к обновлениям app: селекторы
  `.newNoteButton`/`.app-note-editor-01` могут смениться).
- iCloud приватный CloudKit API (ломкость), ADP-аккаунты (вернут шифр).
- Стабильность mapping ID; conflict-copy на двусторонних правках.
- HONOR update/delete через CDP сложнее create (навигация по UI-списку).

## Порядок (второй план детализирует)
1. NoteAdapter + canon Note + хеш.
2. icloud-adapter (обернуть icloud/* в адаптер).
3. honor-read-adapter (БД-ридер в адаптер).
4. honor-write-adapter (cdp_writer + update/delete через CDP).
5. state-store.
6. sync-engine (классификация + conflict-copy + консерв. удаления).
7. scheduler (launchd) + конфиг + логи.
