"""HONOR NoteAdapter: read из локальной БД + write через CDP-drive HonorWorkStation.

read: honor_read (ChaCha20 БД). write: cdp_writer (драйв app, родная крипта+синк).
Требует запущенный HonorWorkStation с --remote-debugging-port (для write).
create доказан; update/delete — Task 10 (CDP UI-навигация).
"""
import time

from ihonor.adapters.honor_read import read_honor_notes
from ihonor.honor.cdp_writer import HonorCdpWriter
from ihonor.note import Note


class HonorAdapter:
    def __init__(self, cdp_port: int = 9222):
        self._port = cdp_port

    def list(self) -> list[Note]:
        return [n for n in read_honor_notes() if not n.deleted]

    def get(self, ext_id: str) -> Note | None:
        for n in self.list():
            if n.ext_id == ext_id:
                return n
        return None

    def create(self, note: Note) -> str:
        w = HonorCdpWriter(self._port)
        w.connect()
        try:
            w.create_note(note.title, note.body_text)
        finally:
            w.close()
        # app сохраняет в БД с задержкой; находим свежую живую заметку по заголовку
        for _ in range(10):
            time.sleep(1.0)
            cands = [n for n in self.list() if n.title == note.title]
            if cands:
                return max(cands, key=lambda n: n.mtime).ext_id
        return ""

    def update(self, ext_id: str, note: Note) -> None:
        cur = self.get(ext_id)
        title = cur.title if cur else note.title
        w = HonorCdpWriter(self._port)
        w.connect()
        try:
            w.update_note(title, note.body_text)
        finally:
            w.close()

    def delete(self, ext_id: str) -> None:
        cur = self.get(ext_id)
        if not cur:
            return
        w = HonorCdpWriter(self._port)
        w.connect()
        try:
            w.delete_note(cur.title)
        finally:
            w.close()
