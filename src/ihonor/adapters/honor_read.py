"""HONOR read: чтение заметок из локальной ChaCha20-БД HonorWorkStation.

Деривация ключа: ihonor.honor.dbkey. Чтение: node@20 + better-sqlite3-multiple-ciphers
(см. honor_read_helper.js). БД копируется в temp (живую не трогаем).
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ihonor.honor.dbkey import derive_db_password
from ihonor.note import Note

NODE = os.environ.get("IHONOR_NODE", "/opt/homebrew/opt/node@20/bin/node")
NODE_MODULES = os.environ.get("IHONOR_NODE_MODULES", "/tmp/honornode/node_modules")
HELPER = str(Path(__file__).parent / "honor_read_helper.js")
DB = os.path.expanduser(
    "~/Library/Containers/com.hihonor.hihonornote/Data/.config/hihonornote/database.sqlite"
)


def read_honor_notes() -> list[Note]:
    tmp = tempfile.mkdtemp()
    try:
        db_copy = os.path.join(tmp, "database.sqlite")
        for suf in ("", "-wal", "-shm"):
            if os.path.exists(DB + suf):
                shutil.copy(DB + suf, db_copy + suf)
        env = dict(os.environ, HONORPW=derive_db_password(), NODE_PATH=NODE_MODULES)
        out = subprocess.check_output([NODE, HELPER, db_copy], env=env, text=True)
        rows = json.loads(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    notes = []
    for r in rows:
        body = (r.get("search_content") or "").strip()
        notes.append(Note(
            ext_id=r["uuid"],
            title=r.get("title") or "",
            body_text=body,
            mtime=r.get("modify_time") or 0,
            deleted=bool(r.get("delete_flag")),
        ))
    return notes
