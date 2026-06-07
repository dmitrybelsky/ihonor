import json
import subprocess
import sys

from ihonor.state_store import StateStore, Pair


def test_statedump_emits_pairs_json(tmp_path):
    db = tmp_path / "state.db"
    st = StateStore(str(db))
    st.upsert(Pair("h1", "i1", "ha", "ia"))
    out = subprocess.check_output(
        [sys.executable, "-m", "ihonor.statedump"],
        env={"IHONOR_STATE_DB": str(db), "PATH": "/usr/bin:/bin"},
        text=True,
    )
    data = json.loads(out)
    assert data == [{"honor_id": "h1", "icloud_id": "i1",
                     "hash_honor": "ha", "hash_icloud": "ia", "fails": 0}]
