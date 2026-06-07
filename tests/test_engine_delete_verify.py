from ihonor.adapter import InMemoryAdapter
from ihonor.engine import SyncEngine
from ihonor.note import Note
from ihonor.state_store import StateStore


class SilentNoDeleteHonor(InMemoryAdapter):
    """delete() молча не удаляет — имитирует сбойную UI-автоматизацию (cliclick)."""
    def delete(self, ext_id: str) -> None:
        pass


def test_delete_not_propagated_when_target_delete_noops(tmp_path):
    honor = SilentNoDeleteHonor()
    icloud = InMemoryAdapter()
    store = StateStore(str(tmp_path / "s.db"))
    eng = SyncEngine(honor, icloud, store)

    honor.create(Note("", "T", "B", 1))
    eng.sync_once()  # пэрит HONOR->iCloud
    assert len(store.all()) == 1
    iid = store.all()[0].icloud_id

    icloud.delete(iid)              # удалили на iCloud
    stats = eng.sync_once()         # honor.delete молча не сработает
    # пара СОХРАНЕНА (не воскрешаем), удаление не засчитано, ошибка записана
    assert len(store.all()) == 1
    assert stats.deleted_honor == 0
    assert any("ещё на месте" in e for e in stats.errors)

    # след. синк НЕ создаёт дубль на iCloud (нет воскрешения)
    stats2 = eng.sync_once()
    assert stats2.created_icloud == 0


def test_delete_propagated_when_target_actually_deletes(tmp_path):
    honor = InMemoryAdapter()       # обычный: delete тумбстонит
    icloud = InMemoryAdapter()
    store = StateStore(str(tmp_path / "s.db"))
    eng = SyncEngine(honor, icloud, store)

    honor.create(Note("", "T", "B", 1))
    eng.sync_once()
    iid = store.all()[0].icloud_id
    icloud.delete(iid)
    stats = eng.sync_once()
    assert stats.deleted_honor == 1
    assert len(store.all()) == 0    # пара снята — удаление подтверждено
