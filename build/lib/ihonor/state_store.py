import sqlite3
from dataclasses import dataclass

_COLS = "honor_id, icloud_id, hash_honor, hash_icloud, fails"


@dataclass
class Pair:
    honor_id: str
    icloud_id: str
    hash_honor: str
    hash_icloud: str
    fails: int = 0  # подряд неудачных HONOR-update (bounded retry, см. engine)


class StateStore:
    def __init__(self, path: str) -> None:
        # check_same_thread=False: движок зовётся из subprocess/одного потока, но GUI-обвязка
        # может дёргать из разных — соединение всё равно используется сериализованно.
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS pair("
            "honor_id TEXT, icloud_id TEXT, hash_honor TEXT, hash_icloud TEXT,"
            "fails INTEGER DEFAULT 0, PRIMARY KEY(honor_id, icloud_id))"
        )
        # миграция старых БД без колонки fails
        cols = {r[1] for r in self._c.execute("PRAGMA table_info(pair)")}
        if "fails" not in cols:
            self._c.execute("ALTER TABLE pair ADD COLUMN fails INTEGER DEFAULT 0")
        self._c.commit()

    def upsert(self, p: Pair) -> None:
        self._c.execute(
            "INSERT INTO pair VALUES(?,?,?,?,?) "
            "ON CONFLICT(honor_id,icloud_id) DO UPDATE SET hash_honor=excluded.hash_honor,"
            "hash_icloud=excluded.hash_icloud, fails=excluded.fails",
            (p.honor_id, p.icloud_id, p.hash_honor, p.hash_icloud, p.fails),
        )
        self._c.commit()

    @staticmethod
    def _row(r) -> Pair:
        return Pair(r[0], r[1], r[2], r[3], r[4])

    def by_honor(self, honor_id: str) -> Pair | None:
        r = self._c.execute(
            f"SELECT {_COLS} FROM pair WHERE honor_id=?", (honor_id,)
        ).fetchone()
        return self._row(r) if r else None

    def by_icloud(self, icloud_id: str) -> Pair | None:
        r = self._c.execute(
            f"SELECT {_COLS} FROM pair WHERE icloud_id=?", (icloud_id,)
        ).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[Pair]:
        return [self._row(r) for r in self._c.execute(f"SELECT {_COLS} FROM pair").fetchall()]

    def remove(self, honor_id: str, icloud_id: str) -> None:
        self._c.execute(
            "DELETE FROM pair WHERE honor_id=? AND icloud_id=?", (honor_id, icloud_id)
        )
        self._c.commit()
