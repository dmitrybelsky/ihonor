"""python -m ihonor.statedump -> JSON списка пар из state.db (для UI)."""
import json
import os
import sys
from dataclasses import asdict

from ihonor.state_store import StateStore

STATE_DB = os.environ.get("IHONOR_STATE_DB", os.path.expanduser("~/.ihonor/state.db"))


def main() -> None:
    if not os.path.exists(STATE_DB):
        json.dump([], sys.stdout)
        return
    store = StateStore(STATE_DB)
    json.dump([asdict(p) for p in store.all()], sys.stdout)


if __name__ == "__main__":
    main()
