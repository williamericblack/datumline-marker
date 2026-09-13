# Capture store

Empty until the first real capture run. Seeded by `.github/workflows/capture.yml`,
not by hand.

Nothing here is scored, graded, ranked or published. See `../README.md`.

Layout:

```
bodies/<ab>/<sha256>.body    full bodies, content addressed, written on first sight only
diffs/<slot>/<ts>.patch      unified diffs on change; slot/key.txt names the target
index/records.ndjson         append-only: every observation from every run
index/daily/<date>.ndjson    append-only daily change index
state/seen.json              key -> last stored digest (mutable by design)
state/cursor.json            where the component sweep resumes (mutable by design)
state/pypi_names.json        cached PyPI name matches (mutable by design)
last_run.json                most recent run summary
```

Everything except the four mutable files above is append-only and enforced by
`../append_only_guard.py`.
