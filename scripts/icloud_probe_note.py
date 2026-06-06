"""Глубокая проба: достать запись типа Note и посмотреть — шифр или открытый текст.

Пагинируем changes/zone по syncToken, пока не встретим recordType=Note,
печатаем все типы и одну Note целиком.
"""
import json

from ihonor.config import Config
from ihonor.icloud.auth import login


def main() -> None:
    cfg = Config.from_env()
    api = login(cfg.icloud_apple_id, cfg.icloud_password)
    ck_base = api.get_webservice_url("ckdatabasews")
    ck_params = dict(api.params)
    url = f"{ck_base}/database/1/com.apple.notes/production/private/changes/zone"

    sync_token = None
    all_types: dict[str, set] = {}
    sample_note = None
    pages = 0

    while pages < 15:
        body = {"zones": [{"zoneID": {"zoneName": "Notes"}, "desiredKeys": None, "syncToken": sync_token}]}
        r = api.session.post(url, params=ck_params, json=body)
        r.raise_for_status()
        z = r.json()["zones"][0]
        recs = z.get("records", [])
        for rec in recs:
            rt = rec.get("recordType", "?")
            all_types.setdefault(rt, set()).update((rec.get("fields") or {}).keys())
            if rt == "Note" and sample_note is None:
                sample_note = rec
        pages += 1
        sync_token = z.get("syncToken")
        if not z.get("moreComing"):
            break

    print(f"pages={pages}")
    print("=== record types and fields ===")
    for rt, fields in sorted(all_types.items()):
        print(f"{rt}: {sorted(fields)}")

    if sample_note:
        print("\n=== SAMPLE Note (raw) ===")
        print(json.dumps(sample_note, indent=2, default=str)[:4000])
    else:
        print("\nНе встретил recordType=Note. Возможно текст в Note_UserSpecific.Note ref.")


if __name__ == "__main__":
    main()
