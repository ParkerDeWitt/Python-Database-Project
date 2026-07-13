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
    assert output == ["OK", "bar", "1", "1", "(nil)"]


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
    db_path = str(tmp_path / "data.db")
    commands = [
        "SET k v",
        "GET k",
        "EXISTS k",
        "MSET a 1 b 2",
        "MGET a b missing",
        "EXPIRE k 100",
        "TTL k",
        "RANGE a b",
        "BEGIN",
        "SET txkey txval",
        "COMMIT",
        "GET txkey",
        "BEGIN",
        "SET txkey2 abort_me",
        "ABORT",
        "EXISTS txkey2",
        "HSET h f v",
        "HGET h f",
        "HGETALL h",
        "LPUSH l a",
        "RPUSH l b",
        "LRANGE l 0 -1",
        "INCR counter",
        "DECR counter",
        "DEL k",
        "FLUSHDB",
        "EXISTS a",
        "EXIT",
    ]
    output = run_cli(db_path, commands)
    assert len(output) == len(commands) - 1  # every line but EXIT replies
    assert output[0] == "OK"  # SET k v
    assert output[1] == "v"  # GET k
    assert output[-2] == "OK"  # FLUSHDB
    assert output[-1] == "0"  # EXISTS a after FLUSHDB
