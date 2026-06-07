# ihonor — двусторонняя синхронизация заметок HONOR ↔ iCloud

Локальный (macOS) движок синхронизации текстовых заметок между **HONOR Notes**
(HonorWorkStation / телефон HONOR) и **iCloud Notes** (Apple Notes.app).

> ⚠️ Исследовательский проект. Использует реверс-инжиниринг приватных механизмов
> HONOR и iCloud на **собственных устройствах автора**. См. [LIMITATIONS.md](LIMITATIONS.md)
> и [дисклеймер](#дисклеймер) — обязательно к прочтению перед использованием.

## Что делает

- Двусторонний синк **текста** заметок (заголовок + тело) HONOR ↔ iCloud.
- Запуск **локально на Mac**. Apple и HONOR сами доставляют изменения в свои облака
  и на телефон — мы драйвим их родные приложения, а не пишем в облака напрямую.
- Сопоставление заметок по стабильным ID (state-store, SQLite), детект изменений по
  хешу контента, **conflict-copy** при двусторонней правке, консервативные удаления.

## Как это работает (кратко)

| Сторона | Чтение | Запись |
|--|--|--|
| **iCloud** | Apple Notes.app через AppleScript (`osascript`) | Notes.app `make/set/delete`; Apple синкает в облако |
| **HONOR** | локальная зашифрованная БД (ChaCha20) через `apsw` (pure-Python) | драйв HonorWorkStation: CDP (`Input.insertText`) + `cliclick` (delete); app пишет родной криптой и синкает |

Прямая запись в облако HONOR **невозможна** (device-enrollment + token-binding +
DB-integrity) — поэтому пишем через UI самого приложения. Детали: [docs/spike/](docs/spike/).

## Требования

- macOS.
- **Apple Notes.app** — залогинен в iCloud (без Advanced Data Protection, иначе шифр).
- **HonorWorkStation** — установлен, залогинен, запущен с CDP:
  `open -a HonorWorkStation --args --remote-debugging-port=9222`.
- `cliclick` (`brew install cliclick`) + разрешение **Accessibility** (для delete на стороне HONOR).
- Python + [uv](https://docs.astral.sh/uv/) (системный pip может быть сломан — используйте `uv`).
- Чтение БД HONOR — pure-Python (`apsw-sqlite3mc`); **node больше не нужен**.

## Запуск

CLI (один цикл):
```bash
uv pip install -e .
# залогинить iCloud Notes.app и поднять HonorWorkStation с --remote-debugging-port=9222
uv run python -m ihonor.runner          # человекочитаемо
uv run python -m ihonor.runner --json   # машинный вывод результата
```

Автозапуск каждые 15 минут — `config/com.ihonor.sync.plist` (launchd) + `scripts/ihonor_tick.sh`.

## macOS-приложение (menu-bar)

Нативный SwiftUI menu-bar агент в `app/` (статус синка, «Sync now», авто-синк,
проверка предусловий, окно Настройки/Логи/Пары). Движок Python забандлен внутрь `.app`
(self-contained, без node). Сборка (нужен Xcode + [xcodegen](https://github.com/yonaskolb/XcodeGen)):
```bash
cd app && xcodegen generate
xcodebuild -project ihonor.xcodeproj -scheme ihonor -configuration Debug build CODE_SIGNING_ALLOWED=NO
```
Дизайн/план: [docs/superpowers/specs/2026-06-07-macos-app-design.md](docs/superpowers/specs/2026-06-07-macos-app-design.md),
[docs/superpowers/plans/2026-06-07-macos-app.md](docs/superpowers/plans/2026-06-07-macos-app.md).

## Ограничения

Текст-only. **Вложения (PDF/DOCX/XLSX/картинки) НЕ синкаются в HONOR** — у desktop-app
нет UI вставки файлов, а прямая запись в облако заблокирована. Полный список в
[LIMITATIONS.md](LIMITATIONS.md).

## Дисклеймер

Проект для образовательных и исследовательских целей. Реверс-инжиниринг выполнен на
устройствах и аккаунтах автора. Реверс-константы шифрования и протоколов (`dbkey.py`,
`honor/cloud_client.py`, `honor/crypto.py`) — артефакты исследования, не персональные
секреты. Использование может нарушать условия обслуживания HONOR/Apple — проверяйте сами.
Без гарантий; используете на свой риск. Не сливайте секреты (`.env`, токены, БД) в git.

## Лицензия

MIT — см. [LICENSE](LICENSE).
