from ihonor.note import Note, content_hash
from ihonor.adapter import NoteAdapter
from ihonor.state_store import StateStore, Pair


class SyncEngine:
    def __init__(self, honor: NoteAdapter, icloud: NoteAdapter, store: StateStore) -> None:
        self.honor = honor
        self.icloud = icloud
        self.store = store

    def sync_once(self) -> None:
        h_notes = {n.ext_id: n for n in self.honor.list() if not n.deleted}
        i_notes = {n.ext_id: n for n in self.icloud.list() if not n.deleted}
        paired_h = {p.honor_id for p in self.store.all()}
        paired_i = {p.icloud_id for p in self.store.all()}

        for hid, hn in h_notes.items():
            if hid not in paired_h:
                iid = self.icloud.create(hn)
                self.store.upsert(Pair(hid, iid, content_hash(hn), content_hash(hn)))
        for iid, ino in i_notes.items():
            if iid not in paired_i:
                hid = self.honor.create(ino)
                self.store.upsert(Pair(hid, iid, content_hash(ino), content_hash(ino)))

        for p in self.store.all():
            hn = h_notes.get(p.honor_id)
            ino = i_notes.get(p.icloud_id)
            if not hn or not ino:
                continue
            hh, ih = content_hash(hn), content_hash(ino)
            h_changed = hh != p.hash_honor
            i_changed = ih != p.hash_icloud
            if h_changed and not i_changed:
                self.icloud.update(p.icloud_id, hn)
                self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, hh))
            elif i_changed and not h_changed:
                try:
                    self.honor.update(p.honor_id, ino)
                    self.store.upsert(Pair(p.honor_id, p.icloud_id, ih, ih))
                except NotImplementedError:
                    pass  # адаптер не поддерживает update (напр. HONOR CDP) — пропуск
            elif h_changed and i_changed:
                conflict = Note("", hn.title + " (conflict)", hn.body_text, hn.mtime)
                self.icloud.create(conflict)
                self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, ih))

        h_ids = {n.ext_id for n in self.honor.list() if not n.deleted}
        i_ids = {n.ext_id for n in self.icloud.list() if not n.deleted}
        for p in self.store.all():
            h_gone = p.honor_id not in h_ids
            i_gone = p.icloud_id not in i_ids
            if h_gone and not i_gone:
                self.icloud.delete(p.icloud_id)
                self.store.remove(p.honor_id)
            elif i_gone and not h_gone:
                try:
                    self.honor.delete(p.honor_id)
                    self.store.remove(p.honor_id)
                except NotImplementedError:
                    pass  # адаптер не поддерживает delete (HONOR CDP) — пропуск
