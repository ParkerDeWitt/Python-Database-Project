# Simple Key-Value Store

A persistent, append-only key-value store with a Redis-style command-line
interface, built for the "Build Your Own Database" project
(https://build-your-own.org/database/).

## Requirements

- Python 3.10+ (no third-party runtime dependencies)
- `pip install -r requirements-dev.txt` only if you want to run tests/lint locally

## Running it

```
python3 main.py
```

By default this reads/writes `./data.db` in the current directory. To use a
different file:

```
python3 main.py --db /path/to/data.db
```

Type commands at STDIN, one per line; replies print to STDOUT. Example
session:

```
SET name parker
OK
GET name
parker
EXISTS name
1
EXIT
```

Data is durable immediately: every write is flushed and `fsync`'d to
`data.db` before the reply is printed, and the log is replayed to rebuild
the in-memory index on the next startup — kill the process and restart it,
and everything you `SET` is still there.

## Project layout

```
main.py              CLI loop: reads STDIN, calls the engine, prints STDOUT
kvstore/
  index.py            Custom hash-table index (no built-in dict/map; array-of-buckets, linear scan within a bucket)
  storage.py           Append-only log (data.db): append + replay
  engine.py             Command parsing/dispatch, transactions, TTL, last-write-wins
  formatting.py         Every reply string the CLI can print, in one place
tests/
  test_index.py, test_storage.py, test_engine.py    unit tests
  test_cli.py                                          black-box tests via subprocess (STDIN/STDOUT), incl. a restart-persistence test
.github/workflows/ci.yml   GitHub Actions: flake8 + black --check + pytest on every push
```

## Command reference & output format

Output conventions follow familiar Redis-CLI behavior, since the command
set is modeled on Redis. `(nil)` means "no value", `(empty)` means "an
empty multi-value result", `1`/`0` are boolean-ish flags, and `ERR <msg>`
is a malformed command.

| Command | Reply |
|---|---|
| `SET <key> <value>` | `OK` |
| `GET <key>` | value, or `(nil)` |
| `EXIT` | (process exits, no reply) |
| `DEL <key>` | `1` if removed, else `0` |
| `EXISTS <key>` | `1` or `0` |
| `MSET <k1> <v1> ...` | `OK` |
| `MGET <k1> <k2> ...` | space-separated values, `(nil)` per missing key |
| `EXPIRE <key> <seconds>` | `1` if key existed, else `0` (seconds <= 0 deletes immediately) |
| `TTL <key>` | seconds remaining, `-1` = no TTL set, `-2` = key doesn't exist |
| `RANGE <start> <end>` | `k1 v1 k2 v2 ...` for string keys in `[start, end]` lexicographically, or `(empty)` |
| `BEGIN` / `COMMIT` / `ABORT` | `OK`, or `ERR ...` if misused |
| `HSET <hash> <field> <value>` | `1` if new field, `0` if overwritten |
| `HGET <hash> <field>` | value, or `(nil)` |
| `HGETALL <hash>` | `f1 v1 f2 v2 ...`, or `(empty)` |
| `LPUSH`/`RPUSH <key> <value>` | new list length (integer) |
| `LRANGE <key> <start> <stop>` | space-separated values (inclusive, negative indices supported), or `(empty)` |
| `INCR`/`DECR <key>` | new integer value |
| `FLUSHDB` | `OK` |

If gradebot expects slightly different wording (e.g. a different nil
token), every reply is generated in `kvstore/formatting.py` — that's the
one file to edit.

### Transactions

`BEGIN` starts buffering; commands inside the block still apply to the
in-memory store immediately (so `GET` inside the block sees your own
uncommitted writes), but nothing is written to `data.db` until `COMMIT`.
`ABORT` rolls the in-memory store back to its state right before `BEGIN`,
and nothing is ever persisted.

### Indexing

`kvstore/index.py` implements the store's own hash table by hand — an
array of buckets, each bucket a linear list of `[key, value]` pairs — and
never touches Python's built-in `dict`/`set`. Hash-type values (`HSET`
etc.) reuse this same structure for their fields; list-type values
(`LPUSH`/`RPUSH`) are backed by a plain array, per the assignment's
allowed designs.

## Running tests & linting locally

```
pip install -r requirements-dev.txt
pytest -v
flake8 kvstore main.py tests
black --check kvstore main.py tests
```

All of this also runs automatically in GitHub Actions on every push (see
`.github/workflows/ci.yml`).

## Getting this into your GitHub repo (step-by-step)

You said you've already created an empty repo on github.com but haven't
used git locally before — here's the whole flow, run from a terminal
**inside this project's folder**:

```
# one-time setup, only if you've never used git on this machine before
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

git init
git add .
git commit -m "Initial implementation of the key-value store"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

Replace the `origin` URL with the actual URL of the repo you created (copy
it from the green "Code" button on the repo's GitHub page). If GitHub asks
you to authenticate, follow its prompt (it will likely ask you to sign in
via a browser or use a personal access token instead of a password).

After that, every time you make more changes:

```
git add .
git commit -m "describe what changed"
git push
```

## Blackbox testing with Gradebot

1. Download the latest `gradebot` release for your OS from
   https://github.com/jh125486/CSCE4350_gradebot/releases and make it
   executable (`chmod +x gradebot` on macOS/Linux).
2. Run it against this project, pointing `--dir` at this folder and `--run`
   at the command that starts your program:

   ```
   ./gradebot project --dir /path/to/this/project --run "python3 main.py"
   ```

   (Use whichever test-suite name your assignment page specifies for
   `project` if it differs.)
3. It will pipe a batch of commands into your program via STDIN and check
   the STDOUT replies against its rubric — no manual interaction needed.
4. Take a screenshot of the rubric table it prints, save it as
   `gradebot_screenshot.png` in the repo root, then:

   ```
   git add gradebot_screenshot.png
   git commit -m "Add gradebot rubric screenshot"
   git push
   ```

## Tagging the final submission

Once everything is committed and pushed, tag the commit you want graded:

```
git tag project
git push origin project
```

Make sure the tagged commit is the one whose state matches what you're
submitting — if you make further changes, move the tag:

```
git tag -f project
git push origin project --force
```
