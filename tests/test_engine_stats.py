from ihonor.adapter import InMemoryAdapter
from ihonor.engine import SyncEngine
from ihonor.note import Note
from ihonor.state_store import StateStore


def _engine(tmp_path):
    honor = InMemoryAdapter()
    icloud = InMemoryAdapter()
    store = StateStore(str(tmp_path / "s.db"))
    return SyncEngine(honor, icloud, store), honor, icloud


def test_stats_counts_creates(tmp_path):
    eng, honor, icloud = _engine(tmp_path)
    icloud.create(Note("", "T1", "B1", 1))
    stats = eng.sync_once()
    assert stats.created_honor == 1
    assert stats.created_icloud == 0
    assert stats.errors == []


def test_stats_zero_on_idempotent_rerun(tmp_path):
    eng, honor, icloud = _engine(tmp_path)
    icloud.create(Note("", "T1", "B1", 1))
    eng.sync_once()
    stats = eng.sync_once()
    assert stats.created_honor == 0
    assert stats.updated_honor == 0
    assert stats.conflicts == 0
