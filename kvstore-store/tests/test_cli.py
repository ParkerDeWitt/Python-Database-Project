"""Black-box style tests: drive main.py exactly the way an automated
grader (or a human at a terminal) would -- via STDIN/STDOUT of a
subprocess, with no interactive prompting required.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN = str(REPO_ROOT / "main.py")


def run_cli(db_path: str, commands: list) -> list:
    stdin_text = "\n".join(commands) + "\n"
    result = subprocess.run(
        [sys.executable, MAIN, "--db", db_path],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return result.stdout.splitlines()


def test_basic_session(tmp_path):
    db_path = str(tmp_path / "data.db")
    output = run_cli(
        db_path,
        ["SET foo bar", "GET foo", "EXISTS foo", "DEL foo", "GET foo", "EXIT"],
    )
    # GET on a missing key is a blank line, so it shows up as "" here.
    assert output == ["OK", "bar", "1", "1", ""]


def test_no_manual_input_required_eof_closes_program(tmp_path):
    db_path = str(tmp_path / "data.db")
    # No EXIT command at all -- program must terminate cleanly on EOF.
    output = run_cli(db_path, ["SET a 1", "GET a"])
    assert output == ["OK", "1"]


def test_persistence_across_process_restarts(tmp_path):
    db_path = str(tmp_path / "data.db")
    run_cli(db_path, ["SET foo bar", "MSET x 1 y 2", "EXIT"])

    # Brand-new process, same data.db -- state must survive.
    output = run_cli(db_path, ["GET foo", "GET x", "GET y", "EXIT"])
    assert output == ["bar", "1", "2"]


def test_full_command_surface_smoke(tmp_path):
    """Exercises every command once, consuming replies according to their
    arity: 'single' commands produce exactly one line, 'fixed' commands
    produce a known number of lines (one per argument), and 'variable'
    commands produce N lines followed by a literal END line.
    """
    db_path = str(tmp_path / "data.db")
    commands = [
        ("SET k v", "single"),
        ("GET k", "single"),
        ("EXISTS k", "single"),
        ("MSET a 1 b 2", "single"),
        ("MGET a b missing", "fixed", 3),
        ("EXPIRE k 100", "single"),
        ("TTL k", "single"),
        ("RANGE a b", "variable"),
        ("BEGIN", "single"),
        ("SET txkey txval", "single"),
        ("COMMIT", "single"),
        ("GET txkey", "single"),
        ("BEGIN", "single"),
        ("SET txkey2 abort_me", "single"),
        ("ABORT", "single"),
        ("EXISTS txkey2", "single"),
        ("HSET h f v", "single"),
        ("HGET h f", "single"),
        ("HGETALL h", "variable"),
        ("LPUSH l a", "single"),
        ("RPUSH l b", "single"),
        ("LRANGE l 0 -1", "variable"),
        ("INCR counter", "single"),
        ("DECR counter", "single"),
        ("DEL k", "single"),
        ("FLUSHDB", "single"),
        ("EXISTS a", "single"),
    ]
    output = run_cli(db_path, [c[0] for c in commands] + ["EXIT"])

    idx = 0
    replies = {}
    for i, entry in enumerate(commands):
        kind = entry[1]
        if kind == "single":
            replies[i] = output[idx]
            idx += 1
        elif kind == "fixed":
            n = entry[2]
            replies[i] = output[idx : idx + n]
            idx += n
        else:  # variable-length, terminated by a literal "END" line
            values = []
            while output[idx] != "END":
                values.append(output[idx])
                idx += 1
            idx += 1  # consume the END line itself
            replies[i] = values
    assert idx == len(output)  # every line accounted for, nothing left over

    assert replies[0] == "OK"  # SET k v
    assert replies[1] == "v"  # GET k
    assert replies[4] == ["1", "2", ""]  # MGET a b missing
    assert replies[7] == ["a", "b"]  # RANGE a b -> keys only
    assert replies[11] == "txval"  # GET txkey after COMMIT
    assert replies[15] == "0"  # EXISTS txkey2 after ABORT
    assert replies[18] == ["f v"]  # HGETALL h
    assert replies[21] == ["a", "b"]  # LRANGE l 0 -1
    assert replies[22] == "1"  # INCR counter
    assert replies[23] == "0"  # DECR counter
    assert replies[len(commands) - 2] == "OK"  # FLUSHDB
    assert replies[len(commands) - 1] == "0"  # EXISTS a after FLUSHDB
