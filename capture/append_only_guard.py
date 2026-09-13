#!/usr/bin/env python3
"""Refuse to commit a capture run that destroys record.

Two invariants, both of them unrecoverable if broken:

  1. The capture store is append-only. A body, a diff, a record line or a daily
     index that was committed before must still be there, byte for byte. The
     only files allowed to change are the ones whose whole job is to change:
     store/state/seen.json and store/last_run.json.

  2. The universes never shrink. A domain or a pattern removed from a universe
     file stops being captured, and the days it was absent cannot be backfilled
     later - the public files we read are served live and nobody archives them
     for us. Retiring a target is done by prefixing the line with `retired:`,
     which keeps it on the record.

Run from the repo root with the capture changes staged or unstaged; it diffs the
working tree against HEAD.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

MUTABLE = {
    # The only files whose whole job is to change.
    "capture/store/state/seen.json",
    "capture/store/state/cursor.json",
    "capture/store/state/pypi_names.json",
    "capture/store/last_run.json",
}
STORE_PREFIX = "capture/store/"
COMPANIES = "capture/universe/companies.txt"
PATTERNS = "capture/universe/component_patterns.json"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def head_blob(path: str) -> str | None:
    r = subprocess.run(["git", "show", "HEAD:" + path], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main() -> int:
    failures: list[str] = []

    # --- 1. store is append-only -------------------------------------------
    status = git("diff", "--name-status", "HEAD", "--", "capture/").strip()
    for line in status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code, path = parts[0], parts[-1]
        if not path.startswith(STORE_PREFIX):
            continue
        if path in MUTABLE:
            continue
        if code.startswith("A"):
            continue  # a new file is the whole point
        if code.startswith("M"):
            failures.append("MODIFIED an existing capture record: %s "
                            "(the store is append-only)" % path)
        elif code.startswith("D"):
            failures.append("DELETED a capture record: %s "
                            "(the store is append-only)" % path)
        elif code.startswith("R"):
            failures.append("RENAMED a capture record: %s "
                            "(the store is append-only)" % path)
        else:
            failures.append("unexpected change %s to %s" % (code, path))

    # Appending to an ndjson index is a modification at the file level, so the
    # indexes are checked by content instead: every line that was there must
    # still be there, in order, as a prefix of the new file.
    for idx in sorted(pathlib.Path("capture/store/index").rglob("*.ndjson")):
        rel = str(idx).replace("\\", "/")
        old = head_blob(rel)
        if old is None:
            continue  # brand new index file
        new = idx.read_text(encoding="utf-8")
        if not new.startswith(old):
            old_lines = old.splitlines()
            new_lines = new.splitlines()
            where = next((i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b),
                         min(len(old_lines), len(new_lines)))
            failures.append(
                "REWROTE index %s: it is no longer an append to what was committed "
                "(first divergence at line %d; %d committed lines, %d now)"
                % (rel, where + 1, len(old_lines), len(new_lines)))
        failures[:] = [f for f in failures
                       if not (f.startswith("MODIFIED an existing capture record: " + rel))]

    # --- 2. universes never shrink -----------------------------------------
    old = head_blob(COMPANIES)
    if old is not None:
        new_lines = set(pathlib.Path(COMPANIES).read_text().splitlines())
        gone = [l for l in old.splitlines()
                if l.strip() and not l.strip().startswith("#")
                and l not in new_lines and ("retired:" + l.strip()) not in
                {n.strip() for n in new_lines}]
        for g in gone:
            failures.append("PRUNED company universe: %r was removed. A dropped domain "
                            "leaves a permanent hole that cannot be backfilled - prefix "
                            "it with `retired:` instead." % g.strip())

    old = head_blob(PATTERNS)
    if old is not None:
        try:
            o, n = json.loads(old), json.loads(pathlib.Path(PATTERNS).read_text())
            for field in ("npm_search_queries", "npm_name_patterns", "pypi_name_patterns"):
                gone = set(o.get(field, [])) - set(n.get(field, []))
                for g in sorted(gone):
                    failures.append("PRUNED %s: %r was removed. Removing a pattern silently "
                                    "drops packages out of the capture set." % (field, g))
        except Exception as e:
            failures.append("could not compare %s against HEAD: %s" % (PATTERNS, e))

    if failures:
        print("APPEND-ONLY GUARD FAILED:")
        for f in failures:
            print("  - " + f)
        return 1

    print("append-only guard OK: store appends only, no universe was pruned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
