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

## Frida-capture попытка (SIP off → attach работает)
- SIP на машине **отключён** → Frida аттачится к hardened app без переподписи/reboot.
- OpenSSL-unpinning (X509_verify_cert→1, SSL_get_verify_result→0, set_verify→NONE) — хуки
  встали, но захват пуст.
- Хуки `SSL_write`/`SSL_read` и `curl_easy_setopt` в ГЛАВНОМ процессе — НЕ фаят на sync.
- Причина: нативный sync-субсистем (`libpcSyncSDKLibrary`) грузится **лениво** (при открытии
  «Заметки»/синке), сетевой I/O идёт **не в главном процессе** (вероятно transient
  utility-процесс через HnOfficeSdk), TLS возможно статически слинкован (свой BoringSSL).
- `HTTPS_PROXY` нативный sync игнорит (читает только метрика-libcurl).
- Чтобы поймать: frida **spawn + child-gating** + ловля загрузки `libpcSyncSDK` в нужном
  процессе, хук на curl/SSL там. Ещё слой; затем реверс ПОДПИСИ запросов (главная неизвестность).

### Оценка cloud-API reverse
Выполнимо (SIP off), но многосессионный нативный RE: lazy-load + child-process + static-TLS +
реверс подписи. Высокая неопределённость на этапе подписи.

## Frida-capture — МЕТОД РАБОТАЕТ (auth вскрыт, data-sync ещё нет)
Рабочая схема (без секретов в репо; токены остаются в /tmp, gitignored):
- Watcher (`/tmp/watcher.py`, БЕЗ child-gating — gating вешал app!) переаттачивается к
  `HnOfficeCenter` при каждом respawn (процесс волатилен).
- Inject (`/tmp/inject.js`): хук `SSL_write`/`SSL_read` в `libssl.1.1.dylib` →
  plaintext ДО шифрования. Обходит pinning и static-TLS. libpcSyncSDK импортит curl/ssl
  динамически → ловится.

### Вскрытый auth-флоу
- `POST https://hnoauth-login-dra.cloud.honor.com/oauth2/v3/silent_token?client_id=211059920&cversion=win_HnID_4.0.4.001`
  → ответ содержит `access_token` (формат `CgB6e3x9...`). client_id=211059920.
- Заголовки запросов: `Authorization: Bearer <access_token>`, `x-hn-dt` (device token),
  `x-hn-cl-pbk` (client public key → запросы ПОДПИСАНЫ ECDSA клиентским ключом).
- Push-канал: `GET https://webpush-dra.cloud.hihonorcloud.com/message?sign=<sig>` (long-poll
  уведомление об изменениях).

### ЕЩЁ НЕ вскрыто (тяжёлое ядро) — data-sync НЕ по HTTP
По HTTP/libssl.1.1 при создании заметки идут ТОЛЬКО: `silent_token` (auth) +
`webpush /message` (notify). Сам **контент заметок синкается НЕ по HTTP** — судя по
`Softbus::MqttCallback::GetSign` / `libcoap-3-openssl` — по **MQTT/CoAP** через Softbus
(CloudLink). Это отдельный протокол-стек.
- Нужно: хук MQTT/CoAP publish в libSoftbus/libcoap (не SSL_write), вскрыть topic+payload.
- `Softbus::CloudLinkService::GetPayloadSign` / `Softbus::HmacSha256` — функции подписи
  найдены, но при триггере не сработали (upload батчится/идёт по MQTT-сессии, не на каждое
  изменение). Подпись формата `keyId:hex` (HMAC-SHA256 кандидат).
- Приватный ключ — вероятно в `libHnKeystoreSDK` (HUKS). Если так → headless-подпись = звать
  их натив (ctypes), как с ключом БД.

### MQTT/CoAP раунд (8 мин батч-capture с правками заметок)
- `coap_add_data` поймана 264x — но это **LAN device-discovery**
  (`coap://<lan-ip>/device_discover`, HONOR Connect/Magic Link между устройствами), НЕ cloud notes.
- `Softbus::CloudLinkService::GetPayloadSign` и `Softbus::HmacSha256` за 8 минут с правками
  заметок **НЕ сработали** ни разу.
- Значит cloud notes data-upload с десктопа: либо pull-based, либо долгий батч-цикл, либо
  идёт по уже установленной нативной MQTT-сессии (точку записи не запинпойнтили).

### ИТОГ: cloud-reverse = крупный отдельный RE-проект (не закрыт в этой сессии)
Захватываемо: auth(silent_token+Bearer), webpush-notify, LAN-discovery, device UDID/account.
НЕ вскрыто: cloud notes data-протокол записи + подпись + keystore. Это HONOR Softbus/CloudLink
нативный фреймворк (ArkNetwork/TcpManager/MQTT/CoAP) — недели реверса, плюс keystore-подпись
скорее всего звать только в нативе. Capture-инфраструктура (Frida unpinning) доказана и
переиспользуема для будущего захода.

## 🎯 CLOUD WRITE-ПРОТОКОЛ ВСКРЫТ ПОЛНОСТЬЮ (REST, не MQTT!)
Прорыв: notes data-sync = обычный **HTTPS REST** на `space-dra.cloud.hihonorcloud.com`
(GRS `space-drcn`), gateway APISIX. Раньше отфильтровывался. Подписи `sign=` НЕТ —
только Bearer + device-токен. Поймана РЕАЛЬНАЯ успешная запись заметки.

### Хост и заголовки (все запросы)
- `https://space-dra.cloud.hihonorcloud.com`
- `Authorization: Bearer <token>` (из silent_token, см. auth-флоу выше)
- `x-hn-dt: <device token>`, `x-hn-sdkVer: P9.0.0.301`, `x-hn-appVer: P9.0.0.301`
- `x-hn-syncVer: 12` (на sync-data), `x-hn-cl-pbk: <client EC pubkey b64>` (на workingKey)

### Поток синка (полная последовательность)
1. `GET /sync/notepad/version` → `{data:{category:[{categoryName:"note",syncSn:49,...},...]}}`
2. `POST /sync/notepad/lock?lockType=1`
3. `GET /sync/notepad/folder/summary?syncSn=N` → `POST /sync/notepad/folder/end`
4. `POST /sync/notepad/lock?lockType=04`
5. `GET /sync/notepad/note/summary?syncSn=49` (pull изменений)
6. **`POST /sync/notepad/note/upstream`** ← ЗАПИСЬ
   body: `{"add":[{"data":"<hex SM4-blob>"}], "update":[...], "remove":[...]}`
   → `{"data":{"addRsp":[{"luid":"…","guid":"…","syncSn":50,"syncTime":…}],...}}`
   (сервер принял заметку, выдал guid + новый syncSn)
7. `POST /sync/notepad/note/end` → `POST /sync/notepad/sync_end`

### Шифрование контента (вскрыто)
- `GET /basic/security/encryption/publicKey` → server EC pubkey (DER SPKI, 0x04 uncompressed,
  256-bit; стек китайский → **SM2**; точную кривую подтвердить при impl).
- `GET /basic/security/encryption/workingKey?keyType=1` → рабочий ключ (hex), завёрнут на
  `x-hn-cl-pbk` (client EC pubkey).
- note `data` = **SM4**(workingKey, note-JSON) в hex.
- **КЛЮЧЕВОЙ ИНСАЙТ для headless:** шлём СВОЙ сгенерированный EC(SM2) pubkey в `x-hn-cl-pbk`
  → сервер заворачивает workingKey на наш ключ → расшифровываем своим private. **Keystore
  приложения НЕ нужен.** Полностью воспроизводимо headless.

### Headless auth — ДОКАЗАНО (`src/ihonor/honor/cloud_client.py`)
- `POST /oauth2/v3/silent_token` `grant_type=service_token` + `service_token`(долгоживущий,
  53симв) + `device_id`(64hex) + `scope` → 200, свежий `access_token`(128) + refresh_token.
- service_token/device_id извлекаются разово из перехвата silent_token-запроса приложения.
- Свежим токеном: `GET /sync/notepad/version`, `publicKey` → 200. ✅

### note-JSON формат — ВСКРЫТ (хук EVP_EncryptUpdate, plaintext до SM4)
camelCase от DB-схемы. Поля: `uuid, title, guid("" для new), folderUuid, summary, favorite,
type(2=text/6=handwrite), hasAttach, labelUuid, defaultNote, unstructGuid, dirty(1), deleteFlag,
createTime, modifyTime, deleteTime, relateNoteUuid, firstAttachUuid, lockStatus,
lockSecurityUuid, description, isTop, hasTodo, hasRecord, background, handwriteBackground,
titleType("edit"), htmlContent("<p class=...>..."), htmlContentUuid, searchContent, slateContent`.
upstream `data` = SM4(workingKey, этот JSON) в hex.

### Контент-шифр — SM4 (хук EVP_CipherInit_ex↔EncryptUpdate по ctx)
- SM4, key=16 байт (= unwrapped workingKey), **iv=16 байт присутствует** → CBC/CTR (НЕ ECB).
  Через openssl 1.1 `EVP_sm4_*` (libcrypto.1.1). Точный режим (CBC vs CTR) — подтвердить
  decrypt-ом перехваченного блоба.

### ЕДИНСТВЕННОЕ остаётся для автономного push
- **unwrap KDF workingKey**: 72-байт blob от `GET workingKey` (завёрнут на x-hn-cl-pbk)
  → 16-байт SM4-ключ. Свой SM2-keypair → обмен → unwrap. Изолированный шаг; вскрыть хуком
  SM2/ECDH-decrypt (EVP_PKEY_decrypt/ECDH_compute_key) в libcrypto.1.1.
- Затем: SM4-encrypt note-JSON → POST upstream (lock→upstream→end→sync_end). Протокол готов.

## Статус HONOR-стороны гейта
- **READ headless: ✅ ДОКАЗАНО** — БД расшифрована, заметки читаются (title/summary/контент).
- **WRITE: не доказано.** Два пути:
  1. Запись в локальную БД (`dirty=1`, версия) + дать приложению синхронизировать в облако.
     Проще, но мутирует реальные заметки и требует управляемого взаимодействия с app.
  2. Реверс облачного Data Sync API (auth-токен + endpoints) для прямой headless-записи.
- **Архитектурное следствие:** HONOR-адаптер = локальная БД + HonorWorkStation как транспорт
  синка. Это сильно проще и надёжнее, чем реверс облачного API. Кандидат на смену дизайна.
