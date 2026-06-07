"""HONOR read: чтение заметок из локальной ChaCha20-БД HonorWorkStation.

Деривация ключа: ihonor.honor.dbkey. Чтение: apsw (apsw-sqlite3mc) — default
cipher chacha20 совпадает с шифром better-sqlite3-multiple-ciphers, которым app
шифрует БД. БД копируется в temp (живую не трогаем, чтобы не цеплять WAL/локи).
"""
import os
import shutil
import tempfile

import apsw

from ihonor.honor.dbkey import derive_db_password
from ihonor.note import Note

DB = os.path.expanduser(
    "~/Library/Containers/com.hihonor.hihonornote/Data/.config/hihonornote/database.sqlite"
)

_COLS = "uuid,title,search_content,html_content,modify_time,delete_flag,type"


def read_rows(db_path: str, key: str) -> list[dict]:
    """Открыть зашифрованную БД и прочитать строки note как list[dict]."""
    conn = apsw.Connection(db_path)
    try:
        conn.execute(f"PRAGMA key='{key}'")
        cur = conn.execute(f"SELECT {_COLS} FROM note")
        names = [d[0] for d in cur.getdescription()]
        return [dict(zip(names, row)) for row in cur]
    finally:
        conn.close()


def rows_to_notes(rows: list[dict]) -> list[Note]:
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


def read_honor_notes() -> list[Note]:
    tmp = tempfile.mkdtemp()
    try:
        db_copy = os.path.join(tmp, "database.sqlite")
        for suf in ("", "-wal", "-shm"):
            if os.path.exists(DB + suf):
                shutil.copy(DB + suf, db_copy + suf)
        rows = read_rows(db_copy, derive_db_password())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows_to_notes(rows)
