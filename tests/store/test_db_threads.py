from __future__ import annotations

import threading
from pathlib import Path

from cloudripr.store.db import StateDB


def test_connection_is_safe_across_threads(tmp_path: Path) -> None:
    """API endpoints run in a thread pool while runs use the same StateDB."""
    db = StateDB(tmp_path / "state.db")
    errors: list[BaseException] = []

    def hammer(n: int) -> None:
        try:
            for i in range(1500):
                db.kv_set(f"k{n}", str(i))
                db.kv_get(f"k{(n + 1) % 6}")
                db.kv_get_json("missing")
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
