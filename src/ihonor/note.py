import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    ext_id: str
    title: str
    body_text: str
    mtime: int
    deleted: bool = False


def content_hash(note: Note) -> str:
    h = hashlib.sha256()
    h.update(note.title.encode("utf-8"))
    h.update(b"\x00")
    h.update(note.body_text.encode("utf-8"))
    return h.hexdigest()
