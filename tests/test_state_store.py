from ihonor.state_store import StateStore, Pair

def test_upsert_and_get(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.upsert(Pair(honor_id="h1", icloud_id="i1", hash_honor="x", hash_icloud="x"))
    p = s.by_honor("h1")
    assert p.icloud_id == "i1" and p.hash_honor == "x"
    assert s.by_icloud("i1").honor_id == "h1"

def test_all_and_delete(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.upsert(Pair(honor_id="h1", icloud_id="i1", hash_honor="a", hash_icloud="a"))
    assert len(s.all()) == 1
    s.remove("h1", "i1")
    assert s.by_honor("h1") is None
