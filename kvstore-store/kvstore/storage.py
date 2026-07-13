"""Append-only persistent log (data.db).

Every mutating command is written to the log as one line of plain text
*before* it is applied to the in-memory index (write-ahead style), and the
line is flushed to the OS immediately so a write is visible to any other
process (including a freshly restarted instance of this program) the
moment the engine reports success back to the caller.

We deliberately flush() without also calling os.fsync(). flush() pushes
the write out of Python's buffer and into the OS's file system right
away, which is what actually matters for "persists across a restart" --
a plain process restart (not a power-loss/crash) will always see
flushed-but-not-fsynced data. fsync() additionally forces the write out
to physical disk, which only protects against power loss mid-write; it
also adds real per-write latency (worse on some systems, e.g. under
antivirus real-time scanning on Windows), so it's skipped here since it
buys durability guarantees this project doesn't need to demonstrate.

On startup the engine replays this file from the beginning, re-running
every logged command through the same dispatch logic used at runtime, so
the in-memory index is rebuilt exactly as if every command had just been
typed again in order. Because later writes are always applied after
earlier ones, replay naturally gives "last write wins" semantics.
"""

from __future__ import annotations

import os
from typing import Iterator, TextIO

DEFAULT_DB_PATH = "data.db"


class Storage:
    """Wraps the append-only log file."""

    def __init__(self, path: str = DEFAULT_DB_PATH) -> None:
        self.path = path
        # Make sure the file exists so replay() and later appends never
        # have to special-case a missing file.
        if not os.path.exists(self.path):
            open(self.path, "a", encoding="utf-8").close()
        self._fh: TextIO = open(self.path, "a", encoding="utf-8")

    def append(self, line: str) -> None:
        """Append one command line to the log and flush it to the OS."""
        self._fh.write(line.rstrip("\n") + "\n")
        self._fh.flush()

    def replay(self) -> Iterator[str]:
        """Yield every logged command line, in the order it was written."""
        with open(self.path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if line:
                    yield line

    def truncate(self) -> None:
        """Empty the log file (used by FLUSHDB, which also clears the
        index -- an empty index replayed from an empty log is consistent).
        """
        self._fh.close()
        open(self.path, "w", encoding="utf-8").close()
        self._fh = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        self._fh.close()
