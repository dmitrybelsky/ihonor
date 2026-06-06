# iCloud Notes — вскрытые endpoints (Phase 0)

Дата: 2026-06-06. Метод: программно через авторизованную сессию `pyicloud`
(`scripts/icloud_discover.py`, `scripts/icloud_probe_note.py`). Без mitmproxy.

## Auth
- `pyicloud.PyiCloudService(apple_id, password, cookie_directory=".icloud-session")`.
- 2FA — один раз, далее доверенная сессия персистится (повторный логин без 2FA). ✓ headless.
- Полезное из сессии: `api.session` (requests.Session с cookies), `api.params`
  (`dsid`, `clientId`, `clientBuildNumber`, `clientMasteringNumber`),
  `api.get_webservice_url("ckdatabasews")`.

## Транспорт
- Заметки = **CloudKit Web Services** (`ckdatabasews`), контейнер `com.apple.notes`,
  база `production`, scope `private`, зона **`Notes`**.
- Базовый URL (пример): `https://p33-ckdatabasews.icloud.com:443`.
- Отдельный `notesws` (p39-notesws) — пробы `/no/collections` и т.п. дают 400, путь мёртв. НЕ использовать.

## Операции (доказано READ)
### LIST / синхронизация изменений
- `records/query` по типу `Note` НЕЛЬЗЯ: `"Type is not marked indexable: Note"`.
- Рабочий путь — **зональные изменения** (как у настоящих клиентов):
  `POST {ck}/database/1/com.apple.notes/production/private/changes/zone`
  body: `{"zones":[{"zoneID":{"zoneName":"Notes"},"desiredKeys":null,"syncToken":<token|null>}]}`
  → `{"zones":[{"records":[...], "syncToken":..., "moreComing":bool}]}`. Пагинация по `syncToken`.
- `zones/list` тоже работает (отдаёт зоны + начальные syncToken).

### Типы записей (зона Notes)
- `Note`: `TitleEncrypted`, `SnippetEncrypted`, `TextDataEncrypted`, `CreationDate`,
  `ModificationDate`, `Folder`(ref), `Deleted`, `ReplicaIDToNotesVersionDataEncrypted` (CRDT) и др.
- `Folder`, `Note_UserSpecific`, `Attachment`, `Media`, `AccountData`.

### Декодирование контента (КЛЮЧЕВОЕ)
Поля помечены типом `ENCRYPTED_BYTES`, но авторизованной сессии сервер отдаёт
РАСШИФРОВАННОЕ (аккаунт без Advanced Data Protection):
- `TitleEncrypted` = **base64(UTF-8)** → просто `base64.b64decode(...).decode()`. ✓ проверено.
- `TextDataEncrypted` = **base64(gzip(protobuf))**. `gzip.decompress(b64decode(...))`.
  Внутри — protobuf Apple Notes (ICNoteData): текст заметки лежит UTF-8-строкой,
  `￼`(U+FFFC) = позиции вложений, далее attribute-runs форматирования. ✓ текст извлекается.

## WRITE — ДОКАЗАНО (`scripts/icloud_write_probe.py`)
Endpoint: `POST {ck}/database/1/com.apple.notes/production/private/records/modify`,
body `{"operations":[{operationType, record}], "zoneID":{"zoneName":"Notes"}}`.

- **CREATE** (`operationType=create`): задаём `recordName`=UUID, `recordType=Note`,
  поля `TitleEncrypted`=base64(utf8), `TextDataEncrypted`=base64(gzip(protobuf)),
  `Folder`/`Folders`=ref на `DefaultFolder-CloudKit`, `CreationDate`/`ModificationDate`,
  `Deleted=0`. → 200, возвращает `recordName` + `recordChangeTag`. ✓
- **UPDATE** (`operationType=update`): `recordName` + `recordChangeTag` (обязателен) +
  изменённые поля. → 200, новый `recordChangeTag`. ✓
- **DELETE** (`operationType=forceDelete`): `{recordName}`. → 200 `{"deleted":true}`. ✓
- CRDT-поля версий (`ReplicaIDToNotesVersionData...`) для CREATE/UPDATE простого
  текста НЕ обязательны — сервер принимает минимальный protobuf и пересериализует.

### Минимальный TextData protobuf (валиден, round-trip подтверждён)
`NoteStoreProto.document(field2) -> Document.note(field3) -> Note{note_text(field2,string),
attribute_run(field5){length(field1)}}`, затем `gzip` + `base64`. Реализация —
`build_note_blob()` в write-probe. Для fidelity (форматирование, вложения, чек-листы)
нужен полный protobuf — отдельная задача сборки.

## Вердикт по iCloud — ГЕЙТ ПРОЙДЕН headless
- READ (list/get/decode): ✅
- WRITE (create/update/delete): ✅
- Остаточные риски: fidelity (богатый контент), Advanced Data Protection (на ADP-аккаунтах
  сервер вернёт реальный шифр — текущий аккаунт без ADP), хрупкость приватного API.
