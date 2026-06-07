"""Один цикл двустороннего синка с реальными адаптерами (локально на Mac).

iCloud = Apple Notes.app (AppleScript), HONOR = локальная БД (read) + CDP-drive (write).
Требует: запущенный HonorWorkStation с --remote-debugging-port (для HONOR write).

Флаги: --json — машинный вывод результата (для GUI). Без флага — человекочитаемо.
"""
import json
import os
import sys
import time

from ihonor.adapters.honor_adapter import HonorAdapter
from ihonor.adapters.icloud_adapter import ICloudAdapter
from ihonor.engine import SyncEngine
from ihonor.logging_setup import setup_logging
from ihonor.state_store import StateStore

STATE_DB = os.environ.get("IHONOR_STATE_DB", os.path.expanduser("~/.ihonor/state.db"))


def run_once(cdp_port: int = 9222) -> dict:
    log = setup_logging()
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    honor = HonorAdapter(cdp_port)
    icloud = ICloudAdapter()
    store = StateStore(STATE_DB)
    engine = SyncEngine(honor, icloud, store)
    stats = engine.sync_once()
    result = {
        "ts": time.time(),
        "ok": not stats.errors,
        "honor": len([n for n in honor.list() if not n.deleted]),
        "icloud": len([n for n in icloud.list() if not n.deleted]),
        "pairs": len(store.all()),
        "created_honor": stats.created_honor,
        "created_icloud": stats.created_icloud,
        "updated_honor": stats.updated_honor,
        "updated_icloud": stats.updated_icloud,
        "conflicts": stats.conflicts,
        "deleted_honor": stats.deleted_honor,
        "deleted_icloud": stats.deleted_icloud,
        "errors": stats.errors,
    }
    log.info("sync_once %s", {k: v for k, v in result.items() if k != "ts"})
    return result


def main() -> None:
    as_json = "--json" in sys.argv[1:]
    try:
        result = run_once()
    except Exception as e:  # noqa: BLE001 — граница процесса, отдаём ошибку в GUI
        result = {"ts": time.time(), "ok": False, "errors": [f"{type(e).__name__}: {e}"]}
        setup_logging().exception("sync_once failed")
        if as_json:
            json.dump(result, sys.stdout)
            sys.exit(1)
        print(f"[ihonor] FAILED: {result['errors'][0]}")
        sys.exit(1)
    if as_json:
        json.dump(result, sys.stdout)
    else:
        print(f"[ihonor] sync_once done: {result}")


if __name__ == "__main__":
    main()
