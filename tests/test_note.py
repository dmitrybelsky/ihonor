from ihonor.note import Note, content_hash

def test_hash_stable_same_content():
    a = Note(ext_id="1", title="T", body_text="B", mtime=100, deleted=False)
    b = Note(ext_id="2", title="T", body_text="B", mtime=999, deleted=False)
    assert content_hash(a) == content_hash(b)

def test_hash_changes_with_body():
    a = Note(ext_id="1", title="T", body_text="B", mtime=100, deleted=False)
    c = Note(ext_id="1", title="T", body_text="B2", mtime=100, deleted=False)
    assert content_hash(a) != content_hash(c)
