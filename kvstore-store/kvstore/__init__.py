"""kvstore: a small persistent, append-only key-value store.

Package layout:
    index.py      - custom in-memory index structure (no built-in dict/map)
    storage.py    - append-only log file (data.db) reader/writer
    engine.py     - command dispatch, transactions, TTL, last-write-wins
    formatting.py - centralizes every string the CLI prints, so the
                    black-box output format can be tuned in one place
"""

__all__ = ["index", "storage", "engine", "formatting"]
