"""Command engine: parses CLI command lines, applies them to the custom
HashIndex, persists mutations to the append-only log, and formats replies.

Design notes
------------
* Every value in the store is wrapped in an `Entry` (type + payload +
  optional expiry). `type` is one of "string", "hash", "list".
* Hash-type values are themselves backed by another `HashIndex` (fields),
  and list-type values are backed by a plain Python list -- both are
  "arrays", never a built-in dict/set.
* Mutating commands are written to the log as their *canonical* form
  before being counted as durable. `EXPIRE key seconds` is translated to
  `EXPIREAT key <absolute-epoch>` before logging/applying, so replaying
  the log later (at a different wall-clock time) still expires the key
  at the correct absolute moment.
* `_apply()` is the single place that mutates the index. Both live
  command execution and startup replay funnel through it, so behavior
  can never drift between "run it now" and "reconstruct it from disk".
* Transactions (BEGIN/COMMIT/ABORT) apply writes to the live index
  immediately (so reads inside the block observe them), but only copy
  their log lines into `data.db` at COMMIT time. ABORT restores a
  snapshot of every key touched during the block.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from . import formatting
from .index import HashIndex
from .storage import Storage


class Entry:
    """One value stored in the top-level index."""

    __slots__ = ("type", "value", "expire_at")

    def __init__(self, type_: str, value, expire_at: Optional[float] = None):
        self.type = type_
        self.value = value
        self.expire_at = expire_at

    def is_expired(self, now: float) -> bool:
        return self.expire_at is not None and now >= self.expire_at


def _clone_entry(entry: Optional[Entry]) -> Optional[Entry]:
    """Deep-enough copy of an Entry for transaction rollback purposes."""
    if entry is None:
        return None
    if entry.type == "hash":
        cloned_inner = HashIndex()
        for field, val in entry.value.items():
            cloned_inner.set(field, val)
        return Entry("hash", cloned_inner, entry.expire_at)
    if entry.type == "list":
        return Entry("list", list(entry.value), entry.expire_at)
    return Entry(entry.type, entry.value, entry.expire_at)


class CommandError(Exception):
    """Raised for malformed commands; caught centrally and turned into an
    ERR reply."""


class Engine:
    def __init__(self, storage: Storage):
        self.index = HashIndex()
        self.storage = storage
        self._in_txn = False
        self._txn_log_buffer: List[str] = []
        self._txn_snapshot_keys: List[str] = []
        self._txn_undo: List[Tuple[str, Optional[Entry]]] = []
        self._load()

    # ------------------------------------------------------------------
    # Startup replay
    # ------------------------------------------------------------------
    def _load(self) -> None:
        for line in self.storage.replay():
            tokens = line.split()
            if not tokens:
                continue
            op, args = tokens[0].upper(), tokens[1:]
            try:
                self._apply(op, args)
            except CommandError:
                # A corrupt/unrecognized log line should not crash
                # startup; skip it rather than losing the rest of the log.
                continue

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def execute(self, line: str) -> Optional[str]:
        """Execute one CLI command line, return the reply string, or None
        if the command was EXIT (caller should terminate)."""
        tokens = line.strip().split()
        if not tokens:
            return formatting.error("empty command")

        op, args = tokens[0].upper(), tokens[1:]

        if op == "EXIT":
            return None

        if op == "BEGIN":
            return self._begin()
        if op == "COMMIT":
            return self._commit()
        if op == "ABORT":
            return self._abort()

        try:
            return self._dispatch(op, args)
        except CommandError as exc:
            return formatting.error(str(exc))

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    def _begin(self) -> str:
        if self._in_txn:
            return formatting.error("BEGIN: transaction already in progress")
        self._in_txn = True
        self._txn_log_buffer = []
        self._txn_snapshot_keys = []
        self._txn_undo = []
        return formatting.ok()

    def _commit(self) -> str:
        if not self._in_txn:
            return formatting.error("COMMIT: no transaction in progress")
        for log_line in self._txn_log_buffer:
            self.storage.append(log_line)
        self._end_txn()
        return formatting.ok()

    def _abort(self) -> str:
        if not self._in_txn:
            return formatting.error("ABORT: no transaction in progress")
        for key, prior in reversed(self._txn_undo):
            if prior is None:
                self.index.delete(key)
            else:
                self.index.set(key, prior)
        self._end_txn()
        return formatting.ok()

    def _end_txn(self) -> None:
        self._in_txn = False
        self._txn_log_buffer = []
        self._txn_snapshot_keys = []
        self._txn_undo = []

    def _snapshot(self, key: str) -> None:
        """Record the pre-mutation state of `key`, the first time (and
        only the first time) it's touched inside the current transaction.
        """
        if not self._in_txn or key in self._txn_snapshot_keys:
            return
        self._txn_snapshot_keys.append(key)
        self._txn_undo.append((key, _clone_entry(self.index.get(key))))

    def _persist(self, log_line: str) -> None:
        """Route a mutation's canonical log line to disk immediately, or
        buffer it until COMMIT if inside a transaction."""
        if self._in_txn:
            self._txn_log_buffer.append(log_line)
        else:
            self.storage.append(log_line)

    # ------------------------------------------------------------------
    # Command dispatch (read commands + write commands)
    # ------------------------------------------------------------------
    def _dispatch(self, op: str, args: List[str]) -> str:
        now = time.time()

        if op == "SET":
            self._require(len(args) == 2, "SET requires <key> <value>")
            key, value = args
            self._snapshot(key)
            self._apply("SET", [key, value])
            self._persist(f"SET {key} {value}")
            return formatting.ok()

        if op == "GET":
            self._require(len(args) == 1, "GET requires <key>")
            return formatting.single(self._get_string(args[0], now))

        if op == "DEL":
            self._require(len(args) == 1, "DEL requires <key>")
            key = args[0]
            existed = self._exists_live(key, now)
            if existed:
                self._snapshot(key)
                self._apply("DEL", [key])
                self._persist(f"DEL {key}")
            return formatting.flag(existed)

        if op == "EXISTS":
            self._require(len(args) == 1, "EXISTS requires <key>")
            return formatting.flag(self._exists_live(args[0], now))

        if op == "MSET":
            self._require(
                len(args) >= 2 and len(args) % 2 == 0,
                "MSET requires an even number of <key> <value> args",
            )
            for key in args[0::2]:
                self._snapshot(key)
            self._apply("MSET", args)
            self._persist("MSET " + " ".join(args))
            return formatting.ok()

        if op == "MGET":
            self._require(len(args) >= 1, "MGET requires at least one <key>")
            return formatting.multi(self._get_string(k, now) for k in args)

        if op == "EXPIRE":
            self._require(len(args) == 2, "EXPIRE requires <key> <seconds>")
            key, seconds_raw = args
            seconds = self._to_int(seconds_raw, "EXPIRE seconds must be an integer")
            if not self._exists_live(key, now):
                return formatting.flag(False)
            self._snapshot(key)
            if seconds <= 0:
                self._apply("DEL", [key])
                self._persist(f"DEL {key}")
            else:
                epoch = int(now) + seconds
                self._apply("EXPIREAT", [key, str(epoch)])
                self._persist(f"EXPIREAT {key} {epoch}")
            return formatting.flag(True)

        if op == "TTL":
            self._require(len(args) == 1, "TTL requires <key>")
            key = args[0]
            entry = self.index.get(key)
            if entry is None or entry.is_expired(now):
                return formatting.integer(-2)
            if entry.expire_at is None:
                return formatting.integer(-1)
            return formatting.integer(max(0, int(entry.expire_at - now)))

        if op == "RANGE":
            self._require(len(args) == 2, "RANGE requires <start> <end>")
            start, end = args
            results = []
            for key in sorted(self.index.keys()):
                if not (start <= key <= end):
                    continue
                entry = self.index.get(key)
                if entry is None or entry.is_expired(now) or entry.type != "string":
                    continue
                results.append((key, entry.value))
            return formatting.pairs(results)

        if op == "HSET":
            self._require(len(args) == 3, "HSET requires <hash> <field> <value>")
            hash_key, field, value = args
            self._snapshot(hash_key)
            is_new_field = self._apply("HSET", [hash_key, field, value])
            self._persist(f"HSET {hash_key} {field} {value}")
            return formatting.flag(is_new_field)

        if op == "HGET":
            self._require(len(args) == 2, "HGET requires <hash> <field>")
            hash_key, field = args
            entry = self._typed_entry(hash_key, "hash", now)
            if entry is None:
                return formatting.nil()
            return formatting.single(entry.value.get(field))

        if op == "HGETALL":
            self._require(len(args) == 1, "HGETALL requires <hash>")
            entry = self._typed_entry(args[0], "hash", now)
            if entry is None:
                return formatting.EMPTY
            return formatting.pairs(list(entry.value.items()))

        if op in ("LPUSH", "RPUSH"):
            self._require(len(args) >= 2, f"{op} requires <key> <value> [value ...]")
            key, values = args[0], args[1:]
            self._snapshot(key)
            new_len = self._apply(op, [key] + values)
            self._persist(f"{op} {key} " + " ".join(values))
            return formatting.integer(new_len)

        if op == "LRANGE":
            self._require(len(args) == 3, "LRANGE requires <key> <start> <stop>")
            key, start_raw, stop_raw = args
            start = self._to_int(start_raw, "LRANGE start must be an integer")
            stop = self._to_int(stop_raw, "LRANGE stop must be an integer")
            entry = self._typed_entry(key, "list", now)
            if entry is None:
                return formatting.EMPTY
            values = _slice_inclusive(entry.value, start, stop)
            return formatting.multi(values) if values else formatting.EMPTY

        if op in ("INCR", "DECR"):
            self._require(len(args) == 1, f"{op} requires <key>")
            key = args[0]
            self._snapshot(key)
            new_value = self._apply(op, [key])
            self._persist(f"{op} {key}")
            return formatting.integer(new_value)

        if op == "FLUSHDB":
            self._require(len(args) == 0, "FLUSHDB takes no arguments")
            if self._in_txn:
                for key in list(self.index.keys()):
                    self._snapshot(key)
            self._apply("FLUSHDB", [])
            self._persist("FLUSHDB")
            return formatting.ok()

        raise CommandError(f"unknown command '{op}'")

    # ------------------------------------------------------------------
    # Core mutation logic, shared by live execution and log replay.
    # Returns a value useful to the caller (new length, whether a hash
    # field was newly created, new INCR/DECR value); ignored by replay.
    # ------------------------------------------------------------------
    def _apply(self, op: str, args: List[str]):
        if op == "SET":
            key, value = args
            self.index.set(key, Entry("string", value))
            return None

        if op == "DEL":
            (key,) = args
            self.index.delete(key)
            return None

        if op == "MSET":
            for i in range(0, len(args), 2):
                key, value = args[i], args[i + 1]
                self.index.set(key, Entry("string", value))
            return None

        if op == "EXPIREAT":
            key, epoch_raw = args
            entry = self.index.get(key)
            if entry is not None:
                entry.expire_at = float(epoch_raw)
            return None

        if op == "HSET":
            hash_key, field, value = args
            entry = self.index.get(hash_key)
            if entry is None:
                entry = Entry("hash", HashIndex())
                self.index.set(hash_key, entry)
            elif entry.type != "hash":
                raise CommandError(f"WRONGTYPE {hash_key} is not a hash")
            is_new = not entry.value.contains(field)
            entry.value.set(field, value)
            return is_new

        if op in ("LPUSH", "RPUSH"):
            key, values = args[0], args[1:]
            entry = self.index.get(key)
            if entry is None:
                entry = Entry("list", [])
                self.index.set(key, entry)
            elif entry.type != "list":
                raise CommandError(f"WRONGTYPE {key} is not a list")
            for value in values:
                if op == "LPUSH":
                    entry.value.insert(0, value)
                else:
                    entry.value.append(value)
            return len(entry.value)

        if op in ("INCR", "DECR"):
            (key,) = args
            entry = self.index.get(key)
            if entry is None:
                current = 0
            elif entry.type != "string":
                raise CommandError(f"WRONGTYPE {key} is not a string")
            else:
                try:
                    current = int(entry.value)
                except ValueError as exc:
                    raise CommandError(f"value at {key} is not an integer") from exc
            new_value = current + 1 if op == "INCR" else current - 1
            self.index.set(key, Entry("string", str(new_value)))
            return new_value

        if op == "FLUSHDB":
            self.index.clear()
            return None

        raise CommandError(f"unknown log op '{op}'")

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _get_string(self, key: str, now: float) -> Optional[str]:
        entry = self.index.get(key)
        if entry is None or entry.is_expired(now) or entry.type != "string":
            return None
        return entry.value

    def _typed_entry(self, key: str, expected_type: str, now: float) -> Optional[Entry]:
        entry = self.index.get(key)
        if entry is None or entry.is_expired(now):
            return None
        if entry.type != expected_type:
            raise CommandError(f"WRONGTYPE {key} is not a {expected_type}")
        return entry

    def _exists_live(self, key: str, now: float) -> bool:
        entry = self.index.get(key)
        return entry is not None and not entry.is_expired(now)

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise CommandError(message)

    @staticmethod
    def _to_int(raw: str, message: str) -> int:
        try:
            return int(raw)
        except ValueError as exc:
            raise CommandError(message) from exc


def _slice_inclusive(values: list, start: int, stop: int) -> list:
    """Redis-style LRANGE: inclusive bounds, negative indices count from
    the end of the list (-1 == last element)."""
    n = len(values)
    if n == 0:
        return []

    def normalize(i: int) -> int:
        return i + n if i < 0 else i

    start = max(0, normalize(start))
    stop = min(n - 1, normalize(stop))
    if start > stop:
        return []
    return values[start : stop + 1]
