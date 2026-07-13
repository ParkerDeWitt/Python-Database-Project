"""Custom in-memory index structure.

Assignment requirement: implement your own index (e.g. an array or linked
list scanned linearly) and do NOT rely on the language's built-in
dictionary/map type.

This module implements a small hash table from scratch:
  * `_buckets` is a plain Python *list* (an array) of fixed size.
  * Each bucket is itself a plain Python *list* of [key, value] pairs.
  * Collisions are resolved with separate chaining -- looking a key up
    inside a bucket is a linear scan, exactly as the assignment allows.

No `dict`, `set`, `collections.OrderedDict`, etc. are used anywhere in
this file. Python `list` objects are arrays, which the assignment
explicitly permits.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

_DEFAULT_BUCKETS = 256


class HashIndex:
    """A minimal hand-rolled hash table (array of buckets, each a linear
    list of key/value pairs). Supports get/set/delete/contains, iteration,
    and clearing -- everything the KV engine needs, with last-write-wins
    semantics enforced by `set()` always overwriting an existing key.
    """

    def __init__(self, num_buckets: int = _DEFAULT_BUCKETS) -> None:
        if num_buckets < 1:
            raise ValueError("num_buckets must be >= 1")
        self._num_buckets = num_buckets
        # Array of buckets; each bucket is an array of [key, value] pairs.
        self._buckets: List[List[list]] = [[] for _ in range(num_buckets)]
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def _hash(self, key: str) -> int:
        """Simple polynomial rolling hash (djb2-style), reduced mod the
        bucket count. Implemented by hand rather than using Python's
        built-in `hash()` object-identity-independent hashing would also
        be acceptable, but doing it manually keeps this fully "our own"
        code end to end.
        """
        h = 5381
        for ch in key:
            h = ((h * 33) + ord(ch)) & 0xFFFFFFFF
        return h % self._num_buckets

    def _bucket_for(self, key: str) -> List[list]:
        return self._buckets[self._hash(key)]

    def get(self, key: str) -> Optional[Any]:
        """Return the value for `key`, or None if absent (linear scan)."""
        bucket = self._bucket_for(key)
        for pair in bucket:
            if pair[0] == key:
                return pair[1]
        return None

    def contains(self, key: str) -> bool:
        bucket = self._bucket_for(key)
        for pair in bucket:
            if pair[0] == key:
                return True
        return False

    def set(self, key: str, value: Any) -> None:
        """Insert or overwrite `key`. Last-write-wins: if the key is
        already present in its bucket, its value is replaced in place;
        otherwise a new [key, value] pair is appended.
        """
        bucket = self._bucket_for(key)
        for pair in bucket:
            if pair[0] == key:
                pair[1] = value
                return
        bucket.append([key, value])
        self._size += 1

    def delete(self, key: str) -> bool:
        """Remove `key` if present. Returns True if it was removed."""
        bucket = self._bucket_for(key)
        for i, pair in enumerate(bucket):
            if pair[0] == key:
                del bucket[i]
                self._size -= 1
                return True
        return False

    def clear(self) -> None:
        """Empty the whole index (used by FLUSHDB)."""
        self._buckets = [[] for _ in range(self._num_buckets)]
        self._size = 0

    def keys(self) -> Iterator[str]:
        for bucket in self._buckets:
            for pair in bucket:
                yield pair[0]

    def items(self) -> Iterator[Tuple[str, Any]]:
        for bucket in self._buckets:
            for pair in bucket:
                yield pair[0], pair[1]
