# Datumline capture

**Capture only.** This subtree fetches public files and writes them down. It does
not score, grade, rank, band, compare, assess, summarise or publish anything, and
it never writes to `docs/`.

That is the point. Marking publishes an opinion about named third parties and
carries the risk that goes with that. Capture publishes nothing and asserts
nothing, so it is legally inert — and that inertness is what got it approved to
run broadly. Anything that turns a captured record into a judgement belongs in a
different program, in a different review.

The inertness is enforced, not just intended: `capture.yml` fails the job if a
capture run has touched anything under `docs/`, or anything outside `capture/`.

## What is captured

**COMPONENTS** — npm and PyPI packages whose names match the MCP patterns in
`universe/component_patterns.json`, discovered from the public npm search API and
the PyPI simple index. Per package: the registry manifest, the declared MCP tool
descriptions and parameter schemas *where the registry document carries them*,
the full version list, and maintainer handles. Nothing is inferred: a package
that declares no MCP surface is recorded as declaring none, and no package
tarball is downloaded to go looking.

**COMPANIES** — the apex domains in `universe/companies.txt`. Per domain:
`/.well-known/security.txt`, `/llms.txt`, `/.well-known/ai-plugin.json`, and the
agent-card paths (`/.well-known/agent.json`, `/.well-known/agent-card.json`,
`/.well-known/ai-agent.json`). A 404 is itself an observation and is recorded;
an HTML app shell served in place of the file is recorded as absent, not as a
capture.

## Rules the capturer holds

- **Public paths only.** Nothing behind a login, paywall or access control. No
  credential is ever sent.
- **robots.txt is honoured.** Fetched once per host and consulted for every path.
  A disallowed path is not fetched and the refusal is recorded, so the hole in
  the record is visible rather than silent.
- **No personal data.** Email addresses are replaced with a stable digest prefix
  (`[redacted-email:ab12cd34ef56]`) before anything reaches disk. The address is
  never stored. The digest is stable, so a maintainer handover or a changed
  security contact still shows up as a diff — which is the part worth capturing —
  without the record holding anyone's address.
- **Full body on first sight, diffs thereafter.** Bodies are content-addressed by
  SHA-256 under `store/bodies/`, so an unchanged body is never written twice. A
  changed body is stored as a unified diff under `store/diffs/`.
- **Every record carries SHA-256, fetch timestamp and source URL.** Two digests
  are kept: `sha256_fetched` over the bytes as received, and `sha256_stored` over
  what was written after redaction. The first is the integrity evidence; the
  second is what the store actually holds.
- **Append-only daily change index.** `store/index/daily/YYYY-MM-DD.ndjson`.
- **Hard stop at 45 minutes or 200MB on the first run.** A truncated run says so
  in `store/last_run.json` rather than looking like a complete one.

## Never prune

`universe/companies.txt` and `universe/component_patterns.json` are **append-only**.

A domain removed from the universe stops being captured, and the days it was
absent **cannot be backfilled** — the public files we read are served live, and
nobody archives them on our behalf. A removal leaves a permanent hole in the
record. The same is true of a discovery pattern: drop one and packages fall out
of the set silently.

To stop fetching a domain, prefix the line with `retired:`. It stays on the
record and stops being fetched. `append_only_guard.py` fails the job on any
removal, and on any modification or deletion of an already-committed record.

## Not an assessment

Presence in a universe file is not a rating, a ranking, a shortlist, a
suspicion, or a statement of any kind about the named package or company. It is
a list of hostnames whose public files are read.

## Running it

```
python capture/capture.py --dry-run                       # discover, write nothing
python capture/capture.py --universes components          # one universe
python capture/capture.py --limit-companies 20            # bounded smoke test
python capture/capture.py                                 # full run, 45min/200MB caps
python capture/append_only_guard.py                       # before committing
```

## Layout

```
capture/
  capture.py                     the capturer
  append_only_guard.py           refuses a run that destroys record
  universe/
    companies.txt                append-only company universe
    component_patterns.json      append-only discovery patterns
  store/
    bodies/<ab>/<sha256>.body    full bodies, content addressed, first sight only
    diffs/<slot>/<ts>.patch      unified diffs on change
    index/records.ndjson         append-only: every observation, every run
    index/daily/<date>.ndjson    append-only daily change index
    state/seen.json              key -> last digest (the one mutable file)
    last_run.json                the most recent run summary
```
