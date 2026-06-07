from ihonor.note import Note
from ihonor.adapter import InMemoryAdapter
from ihonor.state_store import StateStore
from ihonor.engine import SyncEngine

def test_inmemory_crud():
    a = InMemoryAdapter()
    rid = a.create(Note(ext_id="", title="t", body_text="b", mtime=1))
    assert any(n.ext_id == rid for n in a.list())
    a.update(rid, Note(ext_id=rid, title="t2", body_text="b", mtime=2))
    assert a.get(rid).title == "t2"
    a.delete(rid)
    assert all(n.deleted or n.ext_id != rid for n in a.list()) or a.get(rid) is None

def test_new_honor_note_creates_in_icloud(tmp_path):
    honor = InMemoryAdapter(); icloud = InMemoryAdapter()
    honor.create(Note("", "Hello", "body", 1))
    eng = SyncEngine(honor, icloud, StateStore(str(tmp_path/"s.db")))
    eng.sync_once()
    titles = [n.title for n in icloud.list() if not n.deleted]
    assert "Hello" in titles

def test_changed_honor_updates_icloud(tmp_path):
    honor = InMemoryAdapter(); icloud = InMemoryAdapter(); st = StateStore(str(tmp_path/"s.db"))
    hid = honor.create(Note("", "T", "b1", 1))
    eng = SyncEngine(honor, icloud, st); eng.sync_once()
    honor.update(hid, Note(hid, "T", "b2", 2))
    eng.sync_once()
    icn = [n for n in icloud.list() if not n.deleted and n.title=="T"][0]
    assert icn.body_text == "b2"

def test_conflict_both_changed_makes_copy(tmp_path):
    honor=InMemoryAdapter(); icloud=InMemoryAdapter(); st=StateStore(str(tmp_path/"s.db"))
    hid=honor.create(Note("","T","b",1)); eng=SyncEngine(honor,icloud,st); eng.sync_once()
    iid=[n.ext_id for n in icloud.list() if n.title=="T"][0]
    honor.update(hid, Note(hid,"T","H-edit",2))
    icloud.update(iid, Note(iid,"T","I-edit",2))
    eng.sync_once()
    bodies=[n.body_text for n in (honor.list()+icloud.list()) if not n.deleted]
    assert any("H-edit" in b for b in bodies) and any("I-edit" in b for b in bodies)

def test_delete_propagates(tmp_path):
    honor=InMemoryAdapter(); icloud=InMemoryAdapter(); st=StateStore(str(tmp_path/"s.db"))
    hid=honor.create(Note("","T","b",1)); eng=SyncEngine(honor,icloud,st); eng.sync_once()
    honor.delete(hid); eng.sync_once()
    assert all(n.deleted for n in icloud.list())


class NoWriteUpdateAdapter(InMemoryAdapter):
    """Адаптер без update/delete (как HONOR CDP) — кидает NotImplementedError."""
    def update(self, ext_id, note):
        raise NotImplementedError("no update")
    def delete(self, ext_id):
        raise NotImplementedError("no delete")


def test_engine_tolerates_unsupported_honor_update(tmp_path):
    honor = NoWriteUpdateAdapter(); icloud = InMemoryAdapter(); st = StateStore(str(tmp_path/"s.db"))
    hid = honor.create(Note("", "T", "b", 1))
    eng = SyncEngine(honor, icloud, st); eng.sync_once()
    iid = [n.ext_id for n in icloud.list() if n.title == "T"][0]
    # iCloud edited -> engine tries honor.update -> NotImplementedError -> skip (no crash)
    icloud.update(iid, Note(iid, "T", "icloud-edit", 2))
    eng.sync_once()  # must not raise
    assert any(n.title == "T" for n in honor.list())


def test_engine_tolerates_unsupported_honor_delete(tmp_path):
    honor = NoWriteUpdateAdapter(); icloud = InMemoryAdapter(); st = StateStore(str(tmp_path/"s.db"))
    honor.create(Note("", "T", "b", 1))
    eng = SyncEngine(honor, icloud, st); eng.sync_once()
    iid = [n.ext_id for n in icloud.list() if n.title == "T"][0]
    icloud.delete(iid)
    eng.sync_once()  # honor.delete -> NotImplementedError -> skip, no crash
