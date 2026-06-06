# HONOR Notes — разведка (Phase 0)

Дата: 2026-06-06.

## Канал «веб cloud.hihonor.com» — ТУПИК для заметок
- `https://cloud.hihonor.com` → редирект на `/findmydevice/webFindOpenPage.html`.
- Веб-портал Honor Cloud выставляет **только «Поиск устройства»** (定位/播放铃声/丢失模式/擦除数据).
- **Раздела заметок/Notepad на вебе НЕТ.** Нет веб-клиента, дёргающего notes-API →
  перехватывать на вебе нечего (в отличие от iCloud с CloudKit-контейнером заметок).
- Backend HONOR Data Sync держит заметки (синхронизируются с телефона), но публичного
  веб-доступа к ним нет.
- Домены инфраструктуры: `*.hihonor.com`, аккаунт-агриmенты на `agreement.itsec.honor.com`,
  login через HONOR ID (`hnid-*.cloud.hihonor.com`).

## Вывод
Для заметок HONOR нужен перехват трафика **реального синхронизирующего клиента**:
- Канал B: телефон (Notepad) через mitmproxy (риск: certificate pinning).
- Канал A: HONOR Notes Windows-клиент через mitmproxy (нужна Windows-машина).

Веб-проба исключена. Следующий шаг — выбрать B или A и снять трафик Data Sync notes:
auth-flow (HONOR ID + email-2FA → токен) и notes endpoints (list/get/create/update/delete).

## Статус HONOR-стороны гейта
- **НЕ ПРОЙДЕНО** — endpoints не вскрыты. Веб-канал отвергнут, нужен device/client-перехват.
