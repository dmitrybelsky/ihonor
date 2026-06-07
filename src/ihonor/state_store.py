import sqlite3
from dataclasses import dataclass


@dataclass
class Pair:
    honor_id: str
    icloud_id: str
    hash_honor: str
    hash_icloud: str


class StateStore:
    def __init__(self, path: str) -> None:
        self._c = sqlite3.connect(path)
        self._c.execute(
            "CREATE TABLE IF NOT EXISTS pair("
            "honor_id TEXT, icloud_id TEXT, hash_honor TEXT, hash_icloud TEXT,"
            "PRIMARY KEY(honor_id, icloud_id))"
        )
        self._c.commit()

    def upsert(self, p: Pair) -> None:
        self._c.execute(
            "INSERT INTO pair VALUES(?,?,?,?) "
            "ON CONFLICT(honor_id,icloud_id) DO UPDATE SET hash_honor=excluded.hash_honor,"
            "hash_icloud=excluded.hash_icloud",
            (p.honor_id, p.icloud_id, p.hash_honor, p.hash_icloud),
        )
        self._c.commit()

    def _row(self, r) -> Pair:
        return Pair(r[0], r[1], r[2], r[3])

    def by_honor(self, honor_id: str) -> Pair | None:
        r = self._c.execute("SELECT * FROM pair WHERE honor_id=?", (honor_id,)).fetchone()
        return self._row(r) if r else None

    def by_icloud(self, icloud_id: str) -> Pair | None:
        r = self._c.execute("SELECT * FROM pair WHERE icloud_id=?", (icloud_id,)).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[Pair]:
        return [self._row(r) for r in self._c.execute("SELECT * FROM pair").fetchall()]

    def remove(self, honor_id: str) -> None:
        self._c.execute("DELETE FROM pair WHERE honor_id=?", (honor_id,))
        self._c.commit()
