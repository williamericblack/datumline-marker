"""Capture continuity: a missed day must surface as state, not as silence.

The scheduler is best-effort. GitHub's cron can delay a run or skip it
outright, and a run that never happens produces no diff, no commit, and no
alert — the corpus quietly stops accruing while every surface still reads
green. That silence is the failure mode this module exists to remove.

Continuity is tracked separately from the heartbeat on purpose. The
heartbeat answers "did the workflow execute", which stays true even when
the capture inside it collected nothing. This answers the different and
harder question: "did a gas day go uncaptured", which is unrecoverable
once the upstream source overwrites it.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Any

OK = "OK"
FIRST_CAPTURE = "FIRST_CAPTURE"
MISSED_CAPTURE_DAY = "MISSED_CAPTURE_DAY"

SCHEMA = "datumline.capture_state/v1"


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])


def load_state(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not be read as "no days were missed".
        return {}


def missed_days(last_capture: str | None, today: dt.date) -> list[str]:
    """Days strictly between the last capture and today, exclusive of both.

    A same-day re-run and a normal next-day run both yield [] — only a real
    gap produces entries.
    """
    if not last_capture:
        return []
    previous = _date(last_capture)
    gap = (today - previous).days
    if gap <= 1:
        return []
    return [(previous + dt.timedelta(days=n)).isoformat() for n in range(1, gap)]


def evaluate(state: dict[str, Any], today: dt.date) -> dict[str, Any]:
    """Classify this run against the recorded capture history."""
    last = state.get("last_capture_date")
    if not last:
        return {"status": FIRST_CAPTURE, "missed": [], "last_capture_date": None}
    missed = missed_days(last, today)
    return {
        "status": MISSED_CAPTURE_DAY if missed else OK,
        "missed": missed,
        "last_capture_date": last,
    }


def record(
    path: pathlib.Path,
    verdict: dict[str, Any],
    today: dt.date,
    *,
    captured: bool,
    dead_publishers: list[str],
) -> dict[str, Any]:
    """Write the continuity record.

    ``last_capture_date`` advances only when a capture actually sealed. A
    failed run must not mark the day as captured, or the next run computes
    its gap from a day that produced nothing and the miss disappears.
    """
    previous = load_state(path)
    history = list(previous.get("missed_days", []))
    for day in verdict["missed"]:
        if day not in history:
            history.append(day)

    doc = {
        "schema": SCHEMA,
        "status": verdict["status"] if captured else "CAPTURE_FAILED",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "last_capture_date": today.isoformat() if captured else previous.get("last_capture_date"),
        "missed_this_run": verdict["missed"],
        "missed_days": sorted(history),
        "dead_publishers": dead_publishers,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return doc
