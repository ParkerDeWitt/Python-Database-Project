import time

from kvstore.engine import Engine
from kvstore.storage import Storage


def make_engine(tmp_path, name="data.db"):
    return Engine(Storage(str(tmp_path / name)))


def test_set_get(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("SET foo bar") == "OK"
    assert e.execute("GET foo") == "bar"
    assert e.execute("GET missing") == "(nil)"


def test_last_write_wins(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo bar")
    e.execute("SET foo baz")
    assert e.execute("GET foo") == "baz"


def test_del_and_exists(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo bar")
    assert e.execute("EXISTS foo") == "1"
    assert e.execute("DEL foo") == "1"
    assert e.execute("DEL foo") == "0"
    assert e.execute("EXISTS foo") == "0"


def test_mset_mget(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("MSET a 1 b 2 c 3") == "OK"
    assert e.execute("MGET a b c missing") == "1 2 3 (nil)"


def test_expire_and_ttl(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo bar")
    assert e.execute("TTL foo") == "-1"
    assert e.execute("EXPIRE foo 100") == "1"
    ttl = int(e.execute("TTL foo"))
    assert 0 < ttl <= 100
    assert e.execute("EXPIRE missing 100") == "0"


def test_expire_in_past_deletes_immediately(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo bar")
    assert e.execute("EXPIRE foo -1") == "1"
    assert e.execute("EXISTS foo") == "0"


def test_ttl_expiry_hides_value(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo bar")
    e.execute("EXPIRE foo 1")
    # Manually force expiry without sleeping the test suite.
    entry = e.index.get("foo")
    entry.expire_at = time.time() - 1
    assert e.execute("GET foo") == "(nil)"
    assert e.execute("EXISTS foo") == "0"
    assert e.execute("TTL foo") == "-2"


def test_range_query(tmp_path):
    e = make_engine(tmp_path)
    e.execute("MSET apple 1 banana 2 cherry 3 date 4")
    assert e.execute("RANGE banana date") == "banana 2 cherry 3 date 4"
    assert e.execute("RANGE zzz zzzz") == "(empty)"


def test_hash_commands(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("HSET h f1 v1") == "1"  # new field
    assert e.execute("HSET h f1 v2") == "0"  # overwrite
    assert e.execute("HGET h f1") == "v2"
    assert e.execute("HGET h missing") == "(nil)"
    e.execute("HSET h f2 v3")
    reply = e.execute("HGETALL h")
    pairs = reply.split()
    as_dict_pairs = sorted(zip(pairs[0::2], pairs[1::2]))
    assert as_dict_pairs == [("f1", "v2"), ("f2", "v3")]


def test_list_commands(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("RPUSH mylist a") == "1"
    assert e.execute("RPUSH mylist b") == "2"
    assert e.execute("LPUSH mylist z") == "3"
    assert e.execute("LRANGE mylist 0 -1") == "z a b"
    assert e.execute("LRANGE mylist 0 0") == "z"
    assert e.execute("LRANGE nokey 0 -1") == "(empty)"


def test_incr_decr(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("INCR counter") == "1"
    assert e.execute("INCR counter") == "2"
    assert e.execute("DECR counter") == "1"


def test_flushdb(tmp_path):
    e = make_engine(tmp_path)
    e.execute("MSET a 1 b 2")
    assert e.execute("FLUSHDB") == "OK"
    assert e.execute("EXISTS a") == "0"
    assert e.execute("EXISTS b") == "0"


def test_transaction_commit(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("BEGIN") == "OK"
    e.execute("SET foo bar")
    assert e.execute("GET foo") == "bar"  # visible mid-transaction
    assert e.execute("COMMIT") == "OK"
    assert e.execute("GET foo") == "bar"


def test_transaction_abort_rolls_back(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET foo original")
    e.execute("BEGIN")
    e.execute("SET foo changed")
    e.execute("DEL nonexistent")
    assert e.execute("GET foo") == "changed"
    assert e.execute("ABORT") == "OK"
    assert e.execute("GET foo") == "original"


def test_transaction_abort_undoes_new_key(tmp_path):
    e = make_engine(tmp_path)
    e.execute("BEGIN")
    e.execute("SET brandnew value")
    e.execute("ABORT")
    assert e.execute("EXISTS brandnew") == "0"


def test_commit_without_begin_errors(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("COMMIT").startswith("ERR")
    assert e.execute("ABORT").startswith("ERR")


def test_exit_returns_none(tmp_path):
    e = make_engine(tmp_path)
    assert e.execute("EXIT") is None


def test_persistence_across_restart(tmp_path):
    db_path = str(tmp_path / "data.db")
    e1 = Engine(Storage(db_path))
    e1.execute("SET foo bar")
    e1.execute("HSET h f v")
    e1.execute("RPUSH mylist a")
    e1.execute("RPUSH mylist b")
    e1.execute("MSET a 1 b 2")
    e1.execute("DEL b")
    e1.storage.close()

    # Reopen a brand-new engine against the same log file.
    e2 = Engine(Storage(db_path))
    assert e2.execute("GET foo") == "bar"
    assert e2.execute("HGET h f") == "v"
    assert e2.execute("LRANGE mylist 0 -1") == "a b"
    assert e2.execute("GET a") == "1"
    assert e2.execute("EXISTS b") == "0"


def test_transaction_writes_are_persisted_only_on_commit(tmp_path):
    db_path = str(tmp_path / "data.db")
    e1 = Engine(Storage(db_path))
    e1.execute("BEGIN")
    e1.execute("SET foo bar")
    # Not committed yet -- log file should still be empty.
    assert list(e1.storage.replay()) == []
    e1.execute("COMMIT")
    assert list(e1.storage.replay()) == ["SET foo bar"]
    e1.storage.close()

    e2 = Engine(Storage(db_path))
    assert e2.execute("GET foo") == "bar"


def test_wrong_type_errors(tmp_path):
    e = make_engine(tmp_path)
    e.execute("SET strkey value")
    assert e.execute("HSET strkey f v").startswith("ERR")
    assert e.execute("LPUSH strkey v").startswith("ERR")
    e.execute("RPUSH listkey v")
    assert e.execute("INCR listkey").startswith("ERR")
