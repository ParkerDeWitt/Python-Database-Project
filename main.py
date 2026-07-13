#!/usr/bin/env python3
"""CLI entry point for the key-value store.

Reads commands from STDIN, one per line, writes replies to STDOUT, one
per line, and exits cleanly on EXIT or end-of-input. No manual/interactive
prompting is done, so this works unattended under a black-box tester that
pipes a batch of commands in via STDIN.

Usage:
    python main.py                 # uses ./data.db in the current directory
    python main.py --db PATH       # use a specific log file location
"""

from __future__ import annotations

import argparse
import sys

from kvstore.engine import Engine
from kvstore.storage import DEFAULT_DB_PATH, Storage


def _use_line_buffering() -> None:
    """Force line buffering on stdin/stdout regardless of whether this
    process's streams are attached to a terminal or a pipe. When STDIN
    and STDOUT are redirected (exactly the case under a black-box tester
    piping commands in and reading replies out), Python may otherwise
    switch to full block buffering, which can delay when input becomes
    visible to us or when output becomes visible to the reader. Forcing
    line buffering here makes behavior identical whether this program is
    run interactively or driven by an external harness.
    """
    try:
        sys.stdin.reconfigure(line_buffering=True)
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass


def main(argv=None) -> int:
    _use_line_buffering()

    parser = argparse.ArgumentParser(description="A simple persistent key-value store.")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"path to the append-only data file (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    storage = Storage(args.db)
    engine = Engine(storage)

    try:
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            reply = engine.execute(line)
            if reply is None:
                break
            print(reply, flush=True)
    finally:
        storage.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
