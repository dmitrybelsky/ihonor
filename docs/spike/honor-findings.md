# HONOR Notes — вскрытые findings (Phase 0)

Дата: 2026-06-06.

## Канал «веб cloud.hihonor.com» — ТУПИК
- Портал выставляет только «Поиск устройства», раздела заметок на вебе нет. Отвергнут.

## РАБОЧИЙ КАНАЛ: локальный клиент HonorWorkStation (macOS) ✅
Пользователь имеет `HonorWorkStation.app` (bundle `com.hihonor.hihonornote`) —
Electron-клиент, который синхронизирует заметки HONOR Cloud в локальную БД.
Это синхронизирующий клиент → используем его как точку интеграции (без mitmproxy/телефона).

### Хранилище
- БД: `~/Library/Containers/com.hihonor.hihonornote/Data/.config/hihonornote/database.sqlite`
- Шифрование: **better-sqlite3-multiple-ciphers** (`@honor/app-note-main`), дефолтный
  шифр = **ChaCha20 (sqleet)**, НЕ SQLCipher (поэтому sqlcipher CLI не открывает).
- accountData.json: `userName`, `picture`, `proguardAccount`.

### Деривация ключа БД (вскрыто из app.asar → EncryService.getDBSecretKey)
1. `enkey` (32 hex) хранится в:
   - macOS preference `com.hihonor.hihonornote` → `Note.Userkey`
   - и в `config.xml` как `deviceIdPrefix + enkey` (`getRealEnkey` отрезает префикс).
2. Пароль БД = `honorcloud_aead_decrypt(nid=895, enkey, aesKey="0a68afdc$c84b$4f",
   keyMata="dcb36b2f$5d18$4d")` — нативная AEAD из `Frameworks/libSecurityKitNodejs.dylib`
   (экспорт `_honorcloud_aead_decrypt`). encryptTag=zeros, ret=-1 (лишь debug-лог,
   plaintext валиден). Результат = 16-симв utf8 пароль (`getRandmon(8)` hex).
3. Открытие: `better-sqlite3-multiple-ciphers`, `PRAGMA key='<пароль>'` (дефолтный ChaCha20).
   - Реверс-вызов их же длиб через `ctypes` → `scripts/honor_dbkey.py` (без хардкода секретов).
   - Чтение: node@20 + prebuilt `better-sqlite3-multiple-ciphers@11.10.0` (ABI совпадает),
     либо бандл-Electron `ELECTRON_RUN_AS_NODE=1` (но App Sandbox мешает читать вне контейнера).

### Схема `note` (ключевые поля)
`uuid, guid, folder_uuid, account_uuid, title, summary, type, delete_flag, create_time,
modify_time, dirty, max_version, html_content, search_content, slate_content,
slate_modify_time, has_attachment, is_top, lock_status, delete_time`.
- `search_content` = плоский текст, `html_content` = rich, `slate_content` = JSON редактора Slate.
- Метаданные синка: `dirty`, `max_version`, `guid`, `unstruct_guid`.

## Облачный Data Sync — НАТИВНЫЙ (для headless WRITE без app)
- Синк заметок реализован НЕ в JS, а в нативе: `HnOfficeSdk.node` →
  `OfficeCenter/libpcSyncSDKLibrary.dylib` (экспорты `StartSyncData`, `EndSync`,
  `OnUploadSyncStart`, `OnDataSyncEnd`, `SetPollingUrl2Reg`, `ReportSyncEvent`).
- Сеть: бандл **libcurl 4.8 + openssl 1.1** (`OfficeCenter/libcurl*.dylib`, `libssl.1.1`).
- Endpoints резолвятся в рантайме через **GRS SDK** (`libGRSSdk.dylib`) по стране — хардкода мало.
- Запросы, вероятно, подписаны (device-cert / HMAC в нативе) — главный риск headless-реимплементации.
- JS-слой: `note/services/cloud.ts` → `hnOfficeProxy` / `RegisterRecvNoteCloudSyncSwitch`.

### План вскрытия cloud API (динамика)
- libcurl уважает `HTTPS_PROXY` + `SSL_CERT_FILE`/`CURL_CA_BUNDLE` → перехват без root:
  запуск HonorWorkStation с env на mitmproxy + доверенный mitm-CA, триггер синка заметок.
- Снять: GRS-резолв endpoint, auth (HONOR ID access token), формат запроса notes sync
  (list/pull/push), схему подписи. Затем оценить, воспроизводима ли подпись headless.
- Риск: certificate pinning сверх CA-проверки; подпись считается только в нативе.

## Динамика: захват трафика — СТЕНА (cert pinning)
Запуск app с `HTTPS_PROXY` + `SSL_CERT_FILE`(mitm CA) → mitmproxy :8080:
- Перехвачено: `metrics-test-drcn.dt.hihonorcloud.com/magicv1` (libcurl, НЕ пиннит).
- Отвергнуто (свой trust-store, pinning):
  - `hnoauth-login-dra.cloud.honor.com` (OAuth-логин) — `tlsv1 alert unknown ca`.
  - `hnid-dra.platform.hihonorcloud.com` (HONOR ID платформа) — то же.
- Следствие: auth не проходит через proxy → `syncing failed`. `SSL_CERT_FILE` влияет
  только на метрику-libcurl, не на нативный auth/sync SSL (`libHNAccountOauthSdk`, libpcSyncSDK).
- Хосты вскрыты (полезно), но тела/токены/подпись — нет.

### Вывод по cloud-API reverse
Нужно ДЕФИТ pinning: Frida-хуки SSL_verify в нативе running-процесса. На macOS с
hardened runtime + library validation инъекция нетривиальна (возможно нужен SIP off).
Плюс реимплементация нативной подписи запросов. Большой, неопределённый объём.

## Статус HONOR-стороны гейта
- **READ headless: ✅ ДОКАЗАНО** — БД расшифрована, заметки читаются (title/summary/контент).
- **WRITE: не доказано.** Два пути:
  1. Запись в локальную БД (`dirty=1`, версия) + дать приложению синхронизировать в облако.
     Проще, но мутирует реальные заметки и требует управляемого взаимодействия с app.
  2. Реверс облачного Data Sync API (auth-токен + endpoints) для прямой headless-записи.
- **Архитектурное следствие:** HONOR-адаптер = локальная БД + HonorWorkStation как транспорт
  синка. Это сильно проще и надёжнее, чем реверс облачного API. Кандидат на смену дизайна.
