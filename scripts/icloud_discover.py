"""Разведка CloudKit-доступа к заметкам iCloud через авторизованную сессию pyicloud.

Цель Task 2: понять, достижим ли контейнер com.apple.notes через ckdatabasews
без ручного mitmproxy. Печатает webservice-urls, params и пробует zones/list.
"""
import json

from ihonor.config import Config
from ihonor.icloud.auth import login


def main() -> None:
    cfg = Config.from_env()
    api = login(cfg.icloud_apple_id, cfg.icloud_password)

    print("=== webservices ===")
    for name, info in api._webservices.items():
        print(f"{name}: {info.get('url')}")

    print("\n=== params (session) ===")
    print(json.dumps(api.params, indent=2, default=str))

    ck_base = api.get_webservice_url("ckdatabasews")
    notes_base = api.get_webservice_url("notes")
    print(f"\nckdatabasews base: {ck_base}")
    print(f"notes base: {notes_base}")

    ck_params = dict(api.params)

    print("\n--- A) ckdatabasews zones/list (com.apple.notes) ---")
    url = f"{ck_base}/database/1/com.apple.notes/production/private/zones/list"
    print("POST", url)
    try:
        r = api.session.post(url, params=ck_params, json={})
        print("status:", r.status_code)
        print(r.text[:1500])
    except Exception as e:
        print("ERR:", e)

    print("\n--- B) changes/zone for Notes (dump records) ---")
    url = f"{ck_base}/database/1/com.apple.notes/production/private/changes/zone"
    body = {"zones": [{"zoneID": {"zoneName": "Notes"}, "desiredKeys": None, "syncToken": None}]}
    print("POST", url, json.dumps(body))
    try:
        r = api.session.post(url, params=ck_params, json=body)
        print("status:", r.status_code)
        data = r.json()
        zones = data.get("zones", [])
        for z in zones:
            recs = z.get("records", [])
            print(f"zone {z.get('zoneID', {}).get('zoneName')}: {len(recs)} records, moreComing={z.get('moreComing')}")
            # типы записей и их поля
            by_type: dict[str, set] = {}
            for rec in recs:
                rt = rec.get("recordType", "?")
                by_type.setdefault(rt, set()).update((rec.get("fields") or {}).keys())
            for rt, fields in by_type.items():
                print(f"  recordType={rt}  fields={sorted(fields)}")
            # показать одну Note целиком
            for rec in recs:
                if rec.get("recordType") == "Note":
                    print("\n  SAMPLE Note record:")
                    print(json.dumps(rec, indent=2, default=str)[:2500])
                    break
    except Exception as e:
        print("ERR:", e)


if __name__ == "__main__":
    main()
