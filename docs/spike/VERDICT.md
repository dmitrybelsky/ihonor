# Phase 0 — вердикт гейта

Дата: 2026-06-06

| Сторона | list | get | create | update | delete | headless? |
|---------|------|-----|--------|--------|---------|-----------|
| iCloud  |  ✅  | ✅  |   ✅   |   ✅   |   ✅    |    ✅     |
| HONOR   |  ✅  | ✅  |   ✅** |   ✅** |   ✅**  |   ✅      |

\*\* HONOR write-протокол ВСКРЫТ (REST `space-dra.../sync/notepad/note/upstream`,
Bearer-auth, SM2/SM4 контент, свой EC-ключ → keystore не нужен). Поймана реальная
успешная запись (addRsp с guid+syncSn). Осталась реализация SM2/SM4 + Bearer-refresh.
Read — через локальную БД (мгновенно) ИЛИ тот же REST (`/sync/notepad/note/summary`).

\* HONOR read доказан на МЕТОДЕ (расшифровка локальной БД HonorWorkStation), но на
текущей машине Notes-модуль ещё не синхронизировал реальные заметки (`firstStart=1`,
только preset-заметка, `account` пустой). Метод применится к реальным заметкам после
активации синка Notes в приложении.

## iCloud — ГЕЙТ ПРОЙДЕН (полностью headless)
- Транспорт: CloudKit `ckdatabasews`, контейнер `com.apple.notes`, зона `Notes`.
- list = `changes/zone`; create/update/delete = `records/modify`.
- Контент: title=base64, body=base64(gzip(protobuf)); сервер отдаёт расшифровку
  авторизованной сессии (аккаунт без Advanced Data Protection).
- Детали: `docs/spike/icloud-findings.md`. Доказано: `scripts/icloud_write_probe.py`.

## HONOR — МЕТОД ВСКРЫТ, нужна активация синка
- Канал: локальный `HonorWorkStation.app` (Electron) как транспорт облачного синка.
  Веб cloud.hihonor.com заметок не выставляет (тупик).
- БД: `database.sqlite`, шифр ChaCha20 (better-sqlite3-multiple-ciphers).
- Ключ: enkey (preference/config.xml) → нативная `honorcloud_aead_decrypt`
  (`libSecurityKitNodejs.dylib`, nid=895, aesKey/keyMata статичны) → пароль → `PRAGMA key`.
  Деривер без секретов: `scripts/honor_dbkey.py`.
- READ реальных заметок доказан на схеме `note` (uuid/title/search_content/html_content/...).
- Детали: `docs/spike/honor-findings.md`.

## БЛОКЕР для live-валидации HONOR
Notes-модуль HonorWorkStation не синхронизировал реальные заметки (firstStart=1).
Нужно от пользователя: открыть «Заметки» в HonorWorkStation, убедиться что HONOR ID +
Data Sync (заметки) включены, дождаться загрузки реальных заметок из облака. После —
повторно прочитать БД (проверить реальные заметки) и провести live WRITE-тест
(локальная запись + синк приложением → проверка появления на телефоне).

## Итог
- [x] iCloud — гейт пройден.
- [~] HONOR — метод доказан (read), live read+write ожидает активации синка Notes.
- Следующий шаг: пользователь активирует синк Notes → дочитываем реальные заметки →
  WRITE-тест (Path 1) → закрываем гейт HONOR → пишем второй план (сборка движка).

## Ключевые риски на сборку
- iCloud: хрупкость приватного CloudKit API; fidelity богатого контента; ADP-аккаунты.
- HONOR: зависимость от запущенного HonorWorkStation как транспорта; запись в живую БД
  (конфликты/версии `dirty`/`max_version`); обновления приложения могут менять схему/ключ.
- Mapping ID между системами; conflict-copy на двусторонних правках.
