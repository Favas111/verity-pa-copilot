#!/usr/bin/env python3
"""
Run a .sql file through the Snowflake CLI.

    python3 scripts/run_sql.py sql/04_resolvers.sql [connection]

Passes the file's contents to `snow sql -q` as a single argv element, so the
shell never re-interprets quotes, $$ delimiters, or backslashes. Anything
containing a stored procedure body needs this; inline `-q "..."` mangles them.
"""

import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: run_sql.py <file.sql> [connection]")
    path = sys.argv[1]
    conn = sys.argv[2] if len(sys.argv) > 2 else "hackathon"

    with open(path, encoding="utf-8") as f:
        sql = f.read()

    proc = subprocess.run(
        ["snow", "sql", "-c", conn, "-q", sql],
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    if proc.stderr.strip():
        sys.stderr.write(proc.stderr)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
