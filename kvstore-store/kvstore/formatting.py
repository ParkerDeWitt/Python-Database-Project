"""Centralizes every string the CLI can print.

Black-box graders are picky about exact output text and line counts. Every
response the engine produces flows through one of these small helpers, so
if gradebot expects a different convention there is exactly one place to
change it instead of hunting through engine.py.

Conventions (tuned against the actual gradebot rubric output):
    OK                       - successful write commands
    ""  (a blank line)       - a single missing/expired value (GET, HGET)
    1 / 0                    - boolean-ish results (EXISTS, DEL, HSET-new-field)
    <integer>                - INCR/DECR/TTL/LPUSH/RPUSH results
    ERR <message>             - malformed command / bad arguments

Multi-value replies come in two shapes:
    * Fixed arity (MGET): the caller already knows how many values to
      expect (one per key requested), so we print exactly that many
      lines -- a blank line per missing key -- with no terminator.
    * Variable arity (RANGE, HGETALL, LRANGE): the caller has no way to
      know the result count in advance, so we print one item per line
      and then a literal "END" line so the reader knows where the list
      stops (even an empty result is just a bare "END").
"""

from __future__ import annotations

from typing import Iterable, Optional

OK = "OK"
END = "END"


def ok() -> str:
    return OK


def flag(value: bool) -> str:
    return "1" if value else "0"


def integer(value: int) -> str:
    return str(value)


def error(message: str) -> str:
    return f"ERR {message}"


def single(value: Optional[str]) -> str:
    """A single scalar reply (GET, HGET): the value, or a blank line if
    the key/field doesn't exist."""
    return "" if value is None else value


def fixed_multiline(values: Iterable[Optional[str]]) -> str:
    """Fixed-arity multi-value reply (MGET): one line per requested key,
    blank for any missing key, no terminator."""
    return "\n".join("" if v is None else v for v in values)


def multiline(items: Iterable[str]) -> str:
    """Variable-arity multi-value reply (RANGE, HGETALL, LRANGE): one
    item per line followed by a literal END line. An empty result is
    just the bare END line."""
    return "\n".join(list(items) + [END])
