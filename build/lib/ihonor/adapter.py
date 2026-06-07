from typing import Protocol
from ihonor.note import Note


class NoteAdapter(Protocol):
    def list(self) -> list[Note]: ...
    def get(self, ext_id: str) -> Note | None: ...
    def create(self, note: Note) -> str: ...
    def update(self, ext_id: str, note: Note) -> None: ...
    def delete(self, ext_id: str) -> None: ...


class InMemoryAdapter:
    def __init__(self) -> None:
        self._d: dict[str, Note] = {}
        self._seq = 0

    def list(self) -> list[Note]:
        return [n for n in self._d.values()]

    def get(self, ext_id: str) -> Note | None:
        return self._d.get(ext_id)

    def create(self, note: Note) -> str:
        self._seq += 1
        rid = f"m{self._seq}"
        self._d[rid] = Note(rid, note.title, note.body_text, note.mtime, False)
        return rid

    def update(self, ext_id: str, note: Note) -> None:
        self._d[ext_id] = Note(ext_id, note.title, note.body_text, note.mtime, False)

    def delete(self, ext_id: str) -> None:
        if ext_id in self._d:
            cur = self._d[ext_id]
            self._d[ext_id] = Note(ext_id, cur.title, cur.body_text, cur.mtime, True)
