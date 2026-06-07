import apsw
import pytest
from ihonor.adapters.honor_read import read_rows, rows_to_notes


def _make_encrypted_db(path, key):
    c = apsw.Connection(str(path))
    c.execute(f"PRAGMA key='{key}'")
    c.execute(
        "CREATE TABLE note(uuid,title,search_content,html_content,"
        "modify_time,delete_flag,type)"
    )
    c.execute(
        "INSERT INTO note VALUES('u1','Hello','body text','<p>body</p>',123,0,2)"
    )
    c.execute(
        "INSERT INTO note VALUES('u2','Gone','x','<p>x</p>',99,1,2)"
    )
    c.close()


def test_read_rows_decrypts_with_key(tmp_path):
    db = tmp_path / "database.sqlite"
    _make_encrypted_db(db, "deadbeefdeadbeef")
    rows = read_rows(str(db), "deadbeefdeadbeef")
    assert len(rows) == 2
    assert rows[0]["title"] == "Hello"


def test_rows_to_notes_maps_fields():
    rows = [
        {"uuid": "u1", "title": "Hello", "search_content": " body ",
         "html_content": "<p>body</p>", "modify_time": 123, "delete_flag": 0, "type": 2},
        {"uuid": "u2", "title": "Gone", "search_content": "x",
         "html_content": "<p>x</p>", "modify_time": 99, "delete_flag": 1, "type": 2},
    ]
    notes = rows_to_notes(rows)
    assert notes[0].ext_id == "u1"
    assert notes[0].title == "Hello"
    assert notes[0].body_text == "body"  # stripped
    assert notes[0].mtime == 123
    assert notes[0].deleted is False
    assert notes[1].deleted is True


def test_read_rows_wrong_key_raises(tmp_path):
    db = tmp_path / "database.sqlite"
    _make_encrypted_db(db, "deadbeefdeadbeef")
    with pytest.raises(Exception):
        read_rows(str(db), "0000000000000000")


def test_read_rows_rejects_quote_in_key(tmp_path):
    db = tmp_path / "database.sqlite"
    _make_encrypted_db(db, "deadbeefdeadbeef")
    with pytest.raises(ValueError):
        read_rows(str(db), "ab'cd")
