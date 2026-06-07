"""Один цикл двустороннего синка с реальными адаптерами (локально на Mac).

iCloud = Apple Notes.app (AppleScript), HONOR = локальная БД (read) + CDP-drive (write).
Требует: запущенный HonorWorkStation с --remote-debugging-port (для HONOR write).

⚠️ Первый полный прогон создаёт пары для ВСЕХ существующих заметок обеих сторон.
Перед первым прогоном — бэкап заметок. Рекомендуется dry-run / тестовый набор.
"""
import os

from ihonor.adapters.honor_adapter import HonorAdapter
from ihonor.adapters.icloud_adapter import ICloudAdapter
from ihonor.engine import SyncEngine
from ihonor.state_store import StateStore

STATE_DB = os.path.expanduser("~/.ihonor/state.db")


def run_once(cdp_port: int = 9222) -> None:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    honor = HonorAdapter(cdp_port)
    icloud = ICloudAdapter()  # Apple Notes.app via AppleScript
    engine = SyncEngine(honor, icloud, StateStore(STATE_DB))
    engine.sync_once()
    print("[ihonor] sync_once done")


if __name__ == "__main__":
    run_once()
