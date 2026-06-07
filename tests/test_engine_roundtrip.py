"""Регресс: адаптер, который НЕ круглорейсит контент идентично (как iCloud —
сворачивает title в body при чтении), не должен вызывать пинг-понг ложных update.
"""
from ihonor.adapter import InMemoryAdapter
from ihonor.engine import SyncEngine
from ihonor.note import Note
from ihonor.state_store import StateStore


class FoldingICloud(InMemoryAdapter):
    """Имитирует iCloud: read-back сворачивает title в body ('T'/'B' -> body 'T B')."""
    @staticmethod
    def _fold(n: Note) -> Note:
        return Note(n.ext_id, n.title, f"{n.title} {n.body_text}".strip(), n.mtime, n.deleted)

    def list(self) -> list[Note]:
        return [self._fold(n) for n in super().list()]

    def get(self, ext_id: str):
        n = super().get(ext_id)
        return self._fold(n) if n else None


def _eng(tmp_path):
    honor = InMemoryAdapter()
    icloud = FoldingICloud()
    store = StateStore(str(tmp_path / "s.db"))
    return SyncEngine(honor, icloud, store), honor, icloud


def test_create_then_stable_no_pingpong(tmp_path):
    eng, honor, _ = _eng(tmp_path)
    honor.create(Note("", "T", "B", 1))
    eng.sync_once()                 # create на iCloud
    s2 = eng.sync_once()            # должно быть стабильно
    assert s2.updated_honor == 0
    assert s2.updated_icloud == 0


def test_honor_edit_propagates_once_then_stable(tmp_path):
    eng, honor, _ = _eng(tmp_path)
    honor.create(Note("", "T", "B", 1))
    eng.sync_once()
    hid = honor.list()[0].ext_id
    honor.update(hid, Note(hid, "T", "B2", 2))
    s3 = eng.sync_once()            # правка уезжает на iCloud
    assert s3.updated_icloud == 1
    s4 = eng.sync_once()            # СТАБИЛЬНО — без пинг-понга
    assert s4.updated_honor == 0
    assert s4.updated_icloud == 0
