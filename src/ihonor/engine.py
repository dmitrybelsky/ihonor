from dataclasses import dataclass, field

from ihonor.adapter import NoteAdapter
from ihonor.note import Note, content_hash
from ihonor.state_store import StateStore, Pair


@dataclass
class SyncStats:
    created_honor: int = 0
    created_icloud: int = 0
    updated_honor: int = 0
    updated_icloud: int = 0
    conflicts: int = 0
    deleted_honor: int = 0
    deleted_icloud: int = 0
    errors: list[str] = field(default_factory=list)


class SyncEngine:
    def __init__(self, honor: NoteAdapter, icloud: NoteAdapter, store: StateStore) -> None:
        self.honor = honor
        self.icloud = icloud
        self.store = store

    def sync_once(self) -> SyncStats:
        s = SyncStats()
        h_notes = {n.ext_id: n for n in self.honor.list() if not n.deleted}
        i_notes = {n.ext_id: n for n in self.icloud.list() if not n.deleted}
        paired_h = {p.honor_id for p in self.store.all()}
        paired_i = {p.icloud_id for p in self.store.all()}

        for hid, hn in h_notes.items():
            if hid not in paired_h:
                try:
                    iid = self.icloud.create(hn)
                except Exception as e:  # noqa: BLE001 — сбой одной записи не валит весь синк
                    s.errors.append(f"icloud.create({hid}): {e}")
                    continue
                if not iid:  # пустой id — пропуск (без битой пары), повтор в след. цикле
                    s.errors.append(f"icloud.create({hid}): empty id")
                    continue
                actual = self.icloud.get(iid)
                self.store.upsert(Pair(hid, iid, content_hash(hn),
                                       content_hash(actual) if actual else content_hash(hn)))
                s.created_icloud += 1
        for iid, ino in i_notes.items():
            if iid not in paired_i:
                try:
                    hid = self.honor.create(ino)
                except Exception as e:  # noqa: BLE001
                    s.errors.append(f"honor.create({iid}): {e}")
                    continue
                if not hid:
                    s.errors.append(f"honor.create({iid}): empty id")
                    continue
                actual = self.honor.get(hid)
                self.store.upsert(Pair(hid, iid,
                                       content_hash(actual) if actual else content_hash(ino),
                                       content_hash(ino)))
                s.created_honor += 1

        for p in self.store.all():
            hn = h_notes.get(p.honor_id)
            ino = i_notes.get(p.icloud_id)
            if not hn or not ino:
                continue
            hh, ih = content_hash(hn), content_hash(ino)
            h_changed = hh != p.hash_honor
            i_changed = ih != p.hash_icloud
            if h_changed and not i_changed:
                try:
                    self.icloud.update(p.icloud_id, hn)
                    self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, hh))
                    s.updated_icloud += 1
                except Exception as e:  # noqa: BLE001
                    s.errors.append(f"icloud.update({p.icloud_id}): {e}")
            elif i_changed and not h_changed:
                try:
                    self.honor.update(p.honor_id, ino)
                    self.store.upsert(Pair(p.honor_id, p.icloud_id, ih, ih))
                    s.updated_honor += 1
                except Exception as e:  # noqa: BLE001 — HONOR CDP-write может реально упасть
                    s.errors.append(f"honor.update({p.honor_id}): {e}")
            elif h_changed and i_changed:
                if hh == ih:
                    # Обе стороны независимо пришли к ОДНОМУ контенту → не конфликт,
                    # просто синхронизируем хеши пары (без лишней conflict-копии).
                    self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, ih))
                    continue
                # Двусторонняя правка → conflict-copy на iCloud. Копия не пэрится здесь:
                # следующий синк подхватит её как новую и распространит на HONOR (один раз,
                # без зацикливания — хеши пары обновлены до текущих значений).
                try:
                    conflict = Note("", hn.title + " (conflict)", hn.body_text, hn.mtime)
                    self.icloud.create(conflict)
                    self.store.upsert(Pair(p.honor_id, p.icloud_id, hh, ih))
                    s.conflicts += 1
                except Exception as e:  # noqa: BLE001
                    s.errors.append(f"icloud.create(conflict {p.icloud_id}): {e}")

        h_ids = {n.ext_id for n in self.honor.list() if not n.deleted}
        i_ids = {n.ext_id for n in self.icloud.list() if not n.deleted}
        for p in self.store.all():
            h_gone = p.honor_id not in h_ids
            i_gone = p.icloud_id not in i_ids
            if h_gone and not i_gone:
                try:
                    self.icloud.delete(p.icloud_id)
                    # ВЕРИФИЦИРУЕМ удаление: delete() может молча не сработать (UI-автоматизация).
                    # Снимаем пару только если заметка реально исчезла (нет/tombstone) — иначе
                    # оставляем, чтобы НЕ воскресить её на следующем синке (create по непарной).
                    cur = self.icloud.get(p.icloud_id)
                    if cur is None or cur.deleted:
                        self.store.remove(p.honor_id, p.icloud_id)
                        s.deleted_icloud += 1
                    else:
                        s.errors.append(f"icloud.delete({p.icloud_id}): ещё на месте, пара сохранена")
                except Exception as e:  # noqa: BLE001
                    s.errors.append(f"icloud.delete({p.icloud_id}): {e}")
            elif i_gone and not h_gone:
                try:
                    self.honor.delete(p.honor_id)
                    cur = self.honor.get(p.honor_id)
                    if cur is None or cur.deleted:
                        self.store.remove(p.honor_id, p.icloud_id)
                        s.deleted_honor += 1
                    else:
                        s.errors.append(f"honor.delete({p.honor_id}): ещё на месте, пара сохранена")
                except Exception as e:  # noqa: BLE001 — HONOR delete (cliclick) может упасть
                    s.errors.append(f"honor.delete({p.honor_id}): {e}")
        return s
