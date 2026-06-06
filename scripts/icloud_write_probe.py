"""Проба iCloud WRITE: create -> (verify) -> delete throwaway-заметки.

Цель Task 3 (write-половина): доказать, что records/modify принимает запись.
Собираем минимальный Apple Notes protobuf для TextDataEncrypted.
Создаём заметку, печатаем ответ, СРАЗУ удаляем по recordName.
"""
import base64
import gzip
import time
import uuid

from ihonor.config import Config
from ihonor.icloud.auth import login


def _varint(n: int) -> bytes:
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _field_len(num: int, payload: bytes) -> bytes:
    return _varint((num << 3) | 2) + _varint(len(payload)) + payload


def _field_varint(num: int, val: int) -> bytes:
    return _varint(num << 3) + _varint(val)


def build_note_blob(text: str) -> str:
    """Минимальный NoteStoreProto -> Document(field2) -> Note(field3)."""
    text_b = text.encode("utf-8")
    n_units = len(text)  # для ASCII = UTF-16 units; достаточно для пробы
    attr_run = _field_varint(1, n_units)            # AttributeRun.length
    note = _field_len(2, text_b) + _field_len(5, attr_run)  # Note.note_text + attribute_run
    document = _field_len(3, note)                  # Document.note
    store = _field_len(2, document)                 # NoteStoreProto.document
    return base64.b64encode(gzip.compress(store)).decode()


def main() -> None:
    cfg = Config.from_env()
    api = login(cfg.icloud_apple_id, cfg.icloud_password)
    ck = api.get_webservice_url("ckdatabasews")
    params = dict(api.params)
    modify = f"{ck}/database/1/com.apple.notes/production/private/records/modify"

    now = int(time.time() * 1000)
    record_name = str(uuid.uuid4()).upper()
    folder_ref = {
        "recordName": "DefaultFolder-CloudKit",
        "action": "VALIDATE",
        "zoneID": {"zoneName": "Notes"},
    }
    title_b64 = base64.b64encode("ihonor-spike".encode("utf-8")).decode()
    body_b64 = build_note_blob("ihonor-spike test\n")

    create_body = {
        "operations": [{
            "operationType": "create",
            "record": {
                "recordName": record_name,
                "recordType": "Note",
                "fields": {
                    "TitleEncrypted": {"value": title_b64, "type": "ENCRYPTED_BYTES"},
                    "TextDataEncrypted": {"value": body_b64, "type": "ENCRYPTED_BYTES"},
                    "SnippetEncrypted": {"value": "", "type": "ENCRYPTED_BYTES"},
                    "CreationDate": {"value": now, "type": "TIMESTAMP"},
                    "ModificationDate": {"value": now, "type": "TIMESTAMP"},
                    "Deleted": {"value": 0, "type": "INT64"},
                    "Folder": {"value": folder_ref, "type": "REFERENCE"},
                    "Folders": {"value": [folder_ref], "type": "REFERENCE_LIST"},
                },
            },
        }],
        "zoneID": {"zoneName": "Notes"},
    }

    print("=== CREATE ===")
    r = api.session.post(modify, params=params, json=create_body)
    print("status:", r.status_code)
    print(r.text[:2000])

    if r.status_code != 200:
        print("\nCREATE отклонён — фиксируем как риск write-пути.")
        return

    rec = r.json()["records"][0]
    rname = rec.get("recordName")
    change_tag = rec.get("recordChangeTag")
    print(f"\nCREATED recordName={rname} changeTag={change_tag}")

    print("\n=== UPDATE ===")
    upd_body = {
        "operations": [{
            "operationType": "update",
            "record": {
                "recordName": rname,
                "recordChangeTag": change_tag,
                "recordType": "Note",
                "fields": {
                    "TitleEncrypted": {"value": base64.b64encode("ihonor-spike-EDITED".encode()).decode(), "type": "ENCRYPTED_BYTES"},
                    "TextDataEncrypted": {"value": build_note_blob("edited body\n"), "type": "ENCRYPTED_BYTES"},
                    "ModificationDate": {"value": int(time.time() * 1000), "type": "TIMESTAMP"},
                },
            },
        }],
        "zoneID": {"zoneName": "Notes"},
    }
    ru = api.session.post(modify, params=params, json=upd_body)
    print("status:", ru.status_code)
    if ru.status_code == 200:
        urec = ru.json()["records"][0]
        new_title = base64.b64decode(urec["fields"]["TitleEncrypted"]["value"]).decode()
        print("UPDATED title ->", new_title, "newChangeTag=", urec.get("recordChangeTag"))
    else:
        print(ru.text[:800])

    print("\n=== DELETE (cleanup) ===")
    del_body = {
        "operations": [{
            "operationType": "forceDelete",
            "record": {"recordName": rname},
        }],
        "zoneID": {"zoneName": "Notes"},
    }
    r2 = api.session.post(modify, params=params, json=del_body)
    print("status:", r2.status_code)
    print(r2.text[:800])


if __name__ == "__main__":
    main()
