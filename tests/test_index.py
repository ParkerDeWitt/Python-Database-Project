from kvstore.index import HashIndex


def test_set_and_get():
    idx = HashIndex(num_buckets=4)
    idx.set("a", 1)
    idx.set("b", 2)
    assert idx.get("a") == 1
    assert idx.get("b") == 2
    assert idx.get("missing") is None


def test_last_write_wins():
    idx = HashIndex(num_buckets=4)
    idx.set("a", 1)
    idx.set("a", 2)
    assert idx.get("a") == 2
    assert len(idx) == 1  # overwrite, not a new entry


def test_delete():
    idx = HashIndex(num_buckets=4)
    idx.set("a", 1)
    assert idx.delete("a") is True
    assert idx.get("a") is None
    assert idx.delete("a") is False


def test_contains():
    idx = HashIndex(num_buckets=4)
    assert idx.contains("a") is False
    idx.set("a", 1)
    assert idx.contains("a") is True


def test_clear():
    idx = HashIndex(num_buckets=4)
    idx.set("a", 1)
    idx.set("b", 2)
    idx.clear()
    assert len(idx) == 0
    assert idx.get("a") is None


def test_collisions_within_a_bucket():
    # Force everything into bucket 0 with a tiny table so we exercise the
    # linear-scan-within-a-bucket path.
    idx = HashIndex(num_buckets=1)
    idx.set("a", 1)
    idx.set("b", 2)
    idx.set("c", 3)
    assert idx.get("a") == 1
    assert idx.get("b") == 2
    assert idx.get("c") == 3
    idx.delete("b")
    assert idx.get("a") == 1
    assert idx.get("b") is None
    assert idx.get("c") == 3


def test_keys_and_items():
    idx = HashIndex(num_buckets=4)
    idx.set("a", 1)
    idx.set("b", 2)
    assert sorted(idx.keys()) == ["a", "b"]
    assert sorted(idx.items()) == [("a", 1), ("b", 2)]
