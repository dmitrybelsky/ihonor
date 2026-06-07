# Дизайн: ihonor.app — macOS menu-bar агент синка

Дата: 2026-06-07. Статус: утверждается. Надстройка над движком (spec v2 `2026-06-07-honor-icloud-sync-design-v2.md`).

## Цель
Нативное macOS-приложение (menu-bar агент + окно настроек/логов/пар), управляющее
существующим Python-движком синка HONOR ↔ iCloud. Self-contained bundle: Python-движок
внутри .app. Параллельно — убрать зависимость от `node` (чтение БД HONOR на Python).

## Среда / внешние зависимости (не бандлятся)
- **HonorWorkStation** (установлен, залогинен) — держит БД + принимает CDP-write.
- **Apple Notes.app** (залогинен в iCloud, без ADP) — сторона iCloud.
- **cliclick** (`brew install cliclick`) + разрешение **Accessibility** — delete на стороне HONOR.
- `libSecurityKitNodejs.dylib` (внутри установки HonorWorkStation) — деривация ключа БД (ctypes).

Всё перечисленное — внешние app/бинари ОС, бандлить нельзя/не нужно; проверяются в рантайме.

## Архитектура
Нативный SwiftUI .app, два слоя:
1. **Swift UI** — MenuBarExtra + окно (Settings/Logs/Pairs), таймер авто-синка, проверка предусловий.
2. **Python-движок** (существующий, забандленный в .app) — вызывается как subprocess, отдаёт JSON.

```
MenuBarExtra ─┐
Settings/Logs ┼─ SyncController(ObservableObject) ─ EngineBridge ─Process→ [bundled python -m ihonor.runner --json] → JSON
Pairs window ─┘        │
                  Preconditions ── HonorWorkStation+CDP / Accessibility / Notes.app
```
Мост: Swift запускает забандленный `python3 -m ihonor.runner --json`, парсит stdout JSON.
Пары — `python3 -m ihonor.statedump` (читает `~/.ihonor/state.db`). Логи — `~/.ihonor/ihonor.log`.

## Компоненты

### Swift (новый код, каталог `app/`)
- `IhonorApp.swift` — entry; `MenuBarExtra` + `Settings`/`Window` scene.
- `MenuBarView.swift` — статус-строка (цвет: ок/идёт/ошибка), «Sync now», тоггл авто-синк,
  последний результат (honor/icloud/pairs, время), «Open window», Quit.
- `SyncController.swift` (`ObservableObject`) — `runSync()` (вызов моста), публикует
  `@Published lastResult/status/isRunning`; `Timer` для авто-синка по интервалу.
- `Preconditions.swift` — `ensure()`:
  - HonorWorkStation+CDP: проба `GET http://localhost:9222/json`; если нет —
    `open -a HonorWorkStation --args --remote-debugging-port=9222`, ждать готовности.
  - Accessibility: `AXIsProcessTrustedWithOptions` (с промптом).
  - Notes.app: наличие в `/System/Applications` или `/Applications`.
  - Возвращает список невыполненных предусловий с actionable-описанием.
- `EngineBridge.swift` — локатор bundled python (`Contents/Resources/pyengine/bin/python3`)
  и пакета; `Process` exec с таймаутом; `Codec`-декод JSON в `SyncResult`/`[Pair]`.
- `SettingsView.swift` — интервал (Stepper), тоггл авто-синк, тоггл «launch at login»
  (опц.); вкладки **Logs** (tail `ihonor.log`) и **Pairs** (таблица из statedump).
- `Models.swift` — `SyncResult`, `Pair`, `Precondition` (Codable).

### Python (правки существующего движка)
- `src/ihonor/adapters/honor_read.py` — **переписать на `apsw` (apsw-sqlite3mc)**:
  открыть `database.sqlite`, `PRAGMA key='<derived>'` (default cipher chacha20 — проверено),
  читать `note` напрямую. Удаляет node-subprocess. Сигнатура `read_honor_notes() -> list[Note]`
  без изменений (контракт адаптера прежний).
- Удалить `src/ihonor/adapters/honor_read_helper.js` и логику установки `/tmp/honornode`.
- `src/ihonor/runner.py` — флаг `--json`: печатать
  `{ts, ok, honor, icloud, pairs, created, updated, conflicts, deleted, errors:[]}`.
  Без флага — текущий человекочитаемый вывод (обратная совместимость).
- `src/ihonor/statedump.py` (новый) — `python -m ihonor.statedump` → JSON списка пар из
  state.db (`{honor_id, icloud_id, hash_honor, hash_icloud}`).
- `src/ihonor/logging_setup.py` (новый) — файловый лог `~/.ihonor/ihonor.log` (rotating),
  подключается в runner.
- `pyproject.toml` — deps += `apsw-sqlite3mc`. (Уже: `requests`, `websocket-client`.)
- Побочно фикс: `cdp_writer.delete_note` activate по имени процесса `Hihonornote`
  (не `HonorWorkStation`, дающее `-600`).

### Bundle
- Xcode-проект (`app/ihonor.xcodeproj`) + `app/build_pyengine.sh`:
  - скачать python-build-standalone (arm64), распаковать в `Contents/Resources/pyengine/`;
  - `pyengine/bin/pip install <repo>` (ihonor + deps) → relocatable.
  - Build Phase копирует pyengine в bundle. Ad-hoc подпись.
- Результат: `ihonor.app` запускает синк без системного Python/uv/node.

## Поток данных
«Sync now»/Timer → `Preconditions.ensure()` (если не ок — алерт, стоп) → `EngineBridge`
`Process(pyengine python, runner --json)` → JSON → `SyncController` publish → меню/окно +
`UNUserNotification` при `errors`/`conflicts>0`. Pairs/Logs окно: statedump + чтение лога.

## Обработка ошибок
- Предусловие не выполнено → меню в warning-состоянии; «Sync now» открывает алерт с
  кнопками: «Запустить HonorWorkStation», «Открыть Settings → Accessibility».
- Subprocess exit≠0 / `errors[]` непустой → показ ошибки в меню + нотификация; хранится
  last-good результат (не затирается).
- Конфликт (создан conflict-copy) → нотификация.
- Engine не найден в бандле → фатальный алерт при старте.

## Тестирование
- Python: текущие 13 тестов + новые:
  - `honor_read` на apsw (тест с фикстурной зашифрованной БД или skip-if-no-HONOR).
  - форма `runner --json` (мок-адаптеры InMemory → проверка ключей/значений JSON).
  - `statedump` (наполнить state.db → проверить JSON).
- Swift: unit-тест декода JSON (`EngineBridge`) на фикстурах `SyncResult`/`[Pair]`;
  логика `Preconditions` с инъекцией чек-функций. UI — ручная проверка.

## YAGNI / вне скоупа
- Нет UI ввода кредов — путь Notes.app+CDP паролей не требует.
- Нет notarization/Developer ID (bundle для себя, ad-hoc подпись).
- HONOR→iCloud вложения не входят (см. LIMITATIONS).
- iCloud public-link / реверс share-API не входят.

## Порядок реализации (детализирует план)
1. Python: honor_read → apsw (убрать node), тест.
2. Python: `--json`, `statedump`, file-logging, фикс delete activate; тесты.
3. Swift: модели + EngineBridge + декод (unit).
4. Swift: Preconditions (unit).
5. Swift: SyncController + таймер.
6. Swift: MenuBarExtra UI.
7. Swift: Settings/Logs/Pairs окно.
8. Bundle: build_pyengine.sh + Xcode build phase + ad-hoc подпись.
9. E2E ручной прогон.
