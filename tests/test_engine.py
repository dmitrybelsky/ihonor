from ihonor.note import Note
from ihonor.adapter import InMemoryAdapter

def test_inmemory_crud():
    a = InMemoryAdapter()
    rid = a.create(Note(ext_id="", title="t", body_text="b", mtime=1))
    assert any(n.ext_id == rid for n in a.list())
    a.update(rid, Note(ext_id=rid, title="t2", body_text="b", mtime=2))
    assert a.get(rid).title == "t2"
    a.delete(rid)
    assert all(n.deleted or n.ext_id != rid for n in a.list()) or a.get(rid) is None
