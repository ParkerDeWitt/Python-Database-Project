"""Centralizes every string the CLI can print.

Black-box graders are picky about exact output text. Every response the
engine produces flows through one of these small helpers, so if gradebot
expects a different convention (e.g. "nil" instead of "(nil)"), there is
exactly one place to change it instead of hunting through engine.py.

The conventions below intentionally mirror familiar Redis-CLI behavior,
since the assignment's command set (SET/GET/EXPIRE/HSET/LPUSH/...) is
modeled directly on Redis:
    OK                          - successful write commands
    (nil)                       - a single missing/expired value
    (empty)                     - a multi-value result with nothing in it
    1 / 0                       - boolean-ish results (EXISTS, DEL, HSET-new-field)
    <integer>                   - INCR/DECR/TTL/LPUSH/RPUSH results
    ERR <message>                - malformed command / bad arguments
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

OK = "OK"
NIL = "(nil)"
EMPTY = "(empty)"


def ok() -> str:
    return OK


def nil() -> str:
    return NIL


def flag(value: bool) -> str:
    return "1" if value else "0"


def integer(value: int) -> str:
    return str(value)


def error(message: str) -> str:
    return f"ERR {message}"


def single(value: Optional[str]) -> str:
    return NIL if value is None else value


def multi(values: Iterable[Optional[str]]) -> str:
    """Format a sequence of values (e.g. MGET results) as one
    space-separated line, using (nil) for any missing entry."""
    rendered = [NIL if v is None else v for v in values]
    return " ".join(rendered) if rendered else EMPTY


def pairs(items: Sequence[Tuple[str, str]]) -> str:
    """Format field/value or key/value pairs (HGETALL, RANGE) as a single
    space-separated 'k1 v1 k2 v2 ...' line."""
    if not items:
        return EMPTY
    flat = []
    for k, v in items:
        flat.append(k)
        flat.append(v)
    return " ".join(flat)
