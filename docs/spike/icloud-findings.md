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

## ОСТАЁТСЯ доказать (WRITE) — главный риск гейта
- `CREATE/UPDATE/DELETE` через `records/modify`
  (`operations[].operationType` = create/update/forceDelete).
- Сложность: для записи нужно собрать валидный `TextDataEncrypted` (protobuf+gzip+base64)
  и, вероятно, CRDT-поля версий (`ReplicaIDToNotesVersionData...`), плюс `recordChangeTag` для update.
- CREATE простой заметки может пройти с минимумом полей — проверяется отдельно.

## Вердикт по iCloud (промежуточный)
- READ headless: **ПРОЙДЕНО**.
- WRITE headless: **не доказано** — следующий шаг.
