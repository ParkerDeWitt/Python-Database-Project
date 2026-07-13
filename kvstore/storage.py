"""Append-only persistent log (data.db).

Every mutating command is written to the log as one line of plain text
*before* it is applied to the in-memory index (write-ahead style), and the
line is flushed + fsync'd immediately so a write is durable the moment the
engine reports success back to the caller.

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
        """Append one command line to the log and force it to disk."""
        self._fh.write(line.rstrip("\n") + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

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
