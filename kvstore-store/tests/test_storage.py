import os

from kvstore.storage import Storage


def test_creates_file_if_missing(tmp_path):
    path = str(tmp_path / "data.db")
    assert not os.path.exists(path)
    Storage(path)
    assert os.path.exists(path)


def test_append_and_replay(tmp_path):
    path = str(tmp_path / "data.db")
    storage = Storage(path)
    storage.append("SET a 1")
    storage.append("SET b 2")
    storage.close()

    storage2 = Storage(path)
    assert list(storage2.replay()) == ["SET a 1", "SET b 2"]


def test_replay_survives_reopen_without_new_writes(tmp_path):
    path = str(tmp_path / "data.db")
    storage = Storage(path)
    storage.append("SET a 1")
    storage.close()

    for _ in range(3):
        storage = Storage(path)
        assert list(storage.replay()) == ["SET a 1"]
        storage.close()


def test_truncate_empties_log(tmp_path):
    path = str(tmp_path / "data.db")
    storage = Storage(path)
    storage.append("SET a 1")
    storage.truncate()
    assert list(storage.replay()) == []
    storage.append("SET b 2")
    assert list(storage.replay()) == ["SET b 2"]
