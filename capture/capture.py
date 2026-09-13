#!/usr/bin/env python3
"""Datumline capture. CAPTURE ONLY.

This program fetches public files and writes them down. It does not score,
grade, rank, band, compare, assess, summarise, or publish anything, and it
never writes to docs/. That is not an oversight to be fixed later: keeping
capture inert is the reason it was approved, and anything that turns a captured
record into a judgement belongs in a different program with a different review.

Two universes:

  COMPONENTS  npm and PyPI packages whose names match the MCP patterns in
              capture/universe/component_patterns.json. For each: the registry
              manifest, the declared MCP tool descriptions and parameter schemas
              where the registry document carries them, the version list, and
              the maintainer handles.

  COMPANIES   the apex domains in capture/universe/companies.txt. For each:
              /.well-known/security.txt, /llms.txt, /.well-known/ai-plugin.json
              and the agent-card paths.

Rules held by this program:

  * Public paths only. Nothing behind a login, paywall or access control, and no
    credential is ever sent.
  * robots.txt is fetched per host and honoured. A disallowed path is not
    fetched; the refusal is recorded so the hole in the record is visible.
  * No personal data is stored. Email addresses are replaced with a salt-free
    digest prefix before anything is written to disk, so a changed address is
    still detectable as a change without the address being kept.
  * Full body on first sight, unified diff thereafter. Bodies are content
    addressed by SHA-256, so an unchanged body is never written twice.
  * Every record carries SHA-256, fetch timestamp and source URL.
  * The daily change index is append-only.
  * Hard stop on a wall-clock and a byte budget. A truncated run says so in its
    run summary rather than looking like a complete one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

ROOT = pathlib.Path(__file__).resolve().parent
STORE = ROOT / "store"
BODIES = STORE / "bodies"
DIFFS = STORE / "diffs"
INDEX = STORE / "index"
DAILY = INDEX / "daily"
STATE = STORE / "state"
SEEN_PATH = STATE / "seen.json"
CURSOR_PATH = STATE / "cursor.json"
PYPI_NAMES_PATH = STATE / "pypi_names.json"
RECORDS_PATH = INDEX / "records.ndjson"

UA = ("datumline-capture/0.1 (+https://github.com/williamericblack/datumline-marker; "
      "public-files-only; robots-honoured)")

COMPANY_PATHS = (
    ("security.txt", "/.well-known/security.txt"),
    ("llms.txt", "/llms.txt"),
    ("ai-plugin.json", "/.well-known/ai-plugin.json"),
    ("agent-card", "/.well-known/agent.json"),
    ("agent-card", "/.well-known/agent-card.json"),
    ("agent-card", "/.well-known/ai-agent.json"),
)

# Keys whose values are declared MCP surface. Captured verbatim when the
# registry document carries them; recorded as absent when it does not. Nothing
# is inferred and nothing is fetched from a package tarball.
MCP_SURFACE_KEYS = ("mcp", "mcpServers", "mcp_servers", "tools", "toolDescriptions",
                    "x-mcp", "xMcp", "mcpConfig", "server", "capabilities")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_print_lock = Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------
# Personal data
# --------------------------------------------------------------------------

def redact_text(text: str) -> tuple[str, int]:
    """Replace every email address with a stable digest prefix.

    The address itself is never written to disk. The digest is stable across
    runs, so a maintainer handover or a changed security contact still shows up
    as a diff — which is the thing worth capturing — without the record holding
    anyone's address.
    """
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        return "[redacted-email:%s]" % hashlib.sha256(m.group(0).lower().encode()).hexdigest()[:12]

    return EMAIL_RE.sub(sub, text), count


def redact_json(obj, counter: list[int]):
    """Drop email-bearing keys and scrub addresses out of every string value."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in ("email", "e-mail", "author_email", "maintainer_email"):
                if v:
                    counter[0] += 1
                    out[k] = "[redacted-email:%s]" % hashlib.sha256(
                        str(v).lower().encode()).hexdigest()[:12]
                else:
                    out[k] = v
                continue
            out[k] = redact_json(v, counter)
        return out
    if isinstance(obj, list):
        return [redact_json(v, counter) for v in obj]
    if isinstance(obj, str):
        new, n = redact_text(obj)
        counter[0] += n
        return new
    return obj


# --------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------

class Budget:
    """Wall clock and byte ceiling. Exhaustion stops the run, it does not fail it."""

    def __init__(self, max_seconds: int, max_bytes: int):
        self.max_seconds = max_seconds
        self.max_bytes = max_bytes
        self.started = time.monotonic()
        self.bytes = 0
        self._lock = Lock()
        self.stopped_because = None

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def spend(self, n: int) -> None:
        with self._lock:
            self.bytes += n

    def exhausted(self) -> bool:
        with self._lock:
            if self.stopped_because:
                return True
            if self.elapsed() > self.max_seconds:
                self.stopped_because = "wall-clock budget of %ds reached" % self.max_seconds
                return True
            if self.bytes > self.max_bytes:
                self.stopped_because = "byte budget of %d reached" % self.max_bytes
                return True
        return False


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

class Robots:
    """One robots.txt per host, fetched once, honoured for every path."""

    def __init__(self, timeout: int):
        self.timeout = timeout
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = Lock()

    def allowed(self, url: str) -> tuple[bool, str]:
        parts = urllib.parse.urlsplit(url)
        host = "%s://%s" % (parts.scheme, parts.netloc)
        with self._lock:
            have = host in self._cache
            rp = self._cache.get(host)
        if not have:
            rp = self._load(host)
            with self._lock:
                self._cache[host] = rp
        if rp is None:
            # No readable robots.txt is not permission denied; RFC 9309 treats an
            # unreachable or absent robots.txt as unrestricted.
            return True, "no robots.txt"
        try:
            return bool(rp.can_fetch(UA, url)), "robots.txt consulted"
        except Exception:
            return True, "robots.txt unparseable"

    def _load(self, host: str):
        rp = urllib.robotparser.RobotFileParser()
        url = host + "/robots.txt"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                if r.status != 200:
                    return None
                raw = r.read(512_000).decode("utf-8", "replace")
        except Exception:
            return None
        rp.parse(raw.splitlines())
        return rp


def fetch(url: str, timeout: int, max_body: int, accept: str | None = None):
    """GET a public URL. No cookies, no auth, no redirects off the scheme."""
    headers = {"User-Agent": UA, "Accept-Encoding": "identity"}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(max_body + 1)
            truncated = len(body) > max_body
            if truncated:
                body = body[:max_body]
            return {
                "ok": True, "status": r.status, "body": body, "truncated": truncated,
                "content_type": (r.headers.get("Content-Type") or "").split(";")[0].strip(),
                "final_url": r.geturl(),
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": "HTTP %d" % e.code, "body": b"",
                "content_type": "", "final_url": url, "truncated": False}
    except Exception as e:
        return {"ok": False, "status": 0, "error": type(e).__name__ + ": " + str(e)[:200],
                "body": b"", "content_type": "", "final_url": url, "truncated": False}


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

class Store:
    """Content-addressed bodies, append-only indexes, per-key diff history."""

    def __init__(self):
        self.seen = json.loads(SEEN_PATH.read_text()) if SEEN_PATH.exists() else {}
        self._lock = Lock()
        self.records: list[dict] = []
        self.changes: list[dict] = []

    def note(self, rec: dict) -> dict:
        """Record an observation that has no body: a 404, a robots refusal, an
        error. These are real observations about the target and belong in the
        index - a domain that stopped serving its security.txt is exactly the
        kind of change the capture exists to notice, and it is invisible if only
        successful fetches are written down."""
        with self._lock:
            self.records.append(rec)
            if rec.get("change") == "unreachable":
                # We learned nothing about this target. Leave seen.json exactly as
                # it was so the next successful fetch diffs against the last thing
                # we actually saw, and keep it out of the change index.
                return rec
            prior = self.seen.get(rec["key"])
            # A target that was serving a body and now is not is a change.
            if prior is not None and prior.get("sha256_stored") is not None:
                rec["prev_sha256_stored"] = prior.get("sha256_stored")
                self.seen[rec["key"]] = {
                    "sha256_stored": None, "body_path": prior.get("body_path"),
                    "last_seen": rec["fetched_at"], "source_url": rec.get("source_url"),
                    "kind": rec.get("kind"), "universe": rec.get("universe"),
                    "last_change": rec.get("change"),
                }
                self.changes.append(rec)
            elif prior is None:
                self.seen[rec["key"]] = {
                    "sha256_stored": None, "body_path": None,
                    "last_seen": rec["fetched_at"], "source_url": rec.get("source_url"),
                    "kind": rec.get("kind"), "universe": rec.get("universe"),
                    "last_change": rec.get("change"),
                }
                self.changes.append(rec)
        return rec

    def body_path(self, digest: str) -> pathlib.Path:
        return BODIES / digest[:2] / (digest + ".body")

    def write(self, key: str, universe: str, kind: str, source_url: str,
              raw: bytes, stored: bytes, meta: dict) -> dict:
        """Record one observation. Returns the index record."""
        digest_fetched = sha256_bytes(raw)
        digest_stored = sha256_bytes(stored)
        fetched_at = now_iso()

        with self._lock:
            prior = self.seen.get(key)

        rec = {
            "key": key,
            "universe": universe,
            "kind": kind,
            "source_url": source_url,
            "fetched_at": fetched_at,
            "bytes": len(raw),
            "sha256_fetched": digest_fetched,
            "sha256_stored": digest_stored,
        }
        rec.update(meta)

        if prior is None:
            # First sight: full body.
            rec["change"] = "new"
            rec["body_path"] = str(self.body_path(digest_stored).relative_to(ROOT))
            self._put_body(digest_stored, stored)
        elif prior.get("sha256_stored") == digest_stored:
            rec["change"] = "unchanged"
            rec["body_path"] = prior.get("body_path")
        else:
            # Seen before and different: store a diff against the last body, not
            # another copy. The body itself is only written if it is genuinely new
            # content-addressed content we do not already hold.
            rec["change"] = "changed"
            rec["prev_sha256_stored"] = prior.get("sha256_stored")
            rec["body_path"] = prior.get("body_path")
            diff_rel = self._put_diff(key, prior, stored, digest_stored, fetched_at)
            if diff_rel:
                rec["diff_path"] = diff_rel

        with self._lock:
            self.seen[key] = {
                "sha256_stored": digest_stored,
                "body_path": rec.get("body_path"),
                "last_seen": fetched_at,
                "source_url": source_url,
                "kind": kind,
                "universe": universe,
            }
            self.records.append(rec)
            if rec["change"] != "unchanged":
                self.changes.append(rec)
        return rec

    def _put_body(self, digest: str, data: bytes) -> None:
        p = self.body_path(digest)
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def _put_diff(self, key: str, prior: dict, new: bytes, new_digest: str,
                  fetched_at: str) -> str | None:
        old_rel = prior.get("body_path")
        old_bytes = b""
        if old_rel:
            old_p = ROOT / old_rel
            if old_p.exists():
                old_bytes = old_p.read_bytes()
        try:
            old_text = old_bytes.decode("utf-8")
            new_text = new.decode("utf-8")
        except UnicodeDecodeError:
            # Binary: no useful textual diff. Keep the new body in full so the
            # change is still recoverable from the record.
            self._put_body(new_digest, new)
            return None
        diff = "".join(difflib.unified_diff(
            old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile="%s@%s" % (key, prior.get("sha256_stored", "")[:12]),
            tofile="%s@%s" % (key, new_digest[:12]), n=3))
        if not diff:
            return None
        slot = hashlib.sha256(key.encode()).hexdigest()[:16]
        d = DIFFS / slot
        d.mkdir(parents=True, exist_ok=True)
        (d / "key.txt").write_text(key + "\n")
        name = fetched_at.replace(":", "").replace("-", "") + "." + new_digest[:12] + ".patch"
        (d / name).write_text(diff)
        return str((d / name).relative_to(ROOT))

    def flush(self, run: dict) -> dict:
        """Append the run to the indexes. Nothing already written is rewritten."""
        INDEX.mkdir(parents=True, exist_ok=True)
        DAILY.mkdir(parents=True, exist_ok=True)
        STATE.mkdir(parents=True, exist_ok=True)

        with RECORDS_PATH.open("a", encoding="utf-8") as fh:
            for r in self.records:
                fh.write(json.dumps(r, sort_keys=True) + "\n")

        day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        daily_path = DAILY / (day + ".ndjson")
        with daily_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"_run": run, "type": "run-start"}, sort_keys=True) + "\n")
            for r in self.changes:
                fh.write(json.dumps(r, sort_keys=True) + "\n")

        SEEN_PATH.write_text(json.dumps(self.seen, indent=1, sort_keys=True))
        return {"daily_index": str(daily_path.relative_to(ROOT)),
                "records_appended": len(self.records),
                "changes_appended": len(self.changes)}


# --------------------------------------------------------------------------
# Universes
# --------------------------------------------------------------------------

def load_companies() -> list[str]:
    out = []
    for line in (ROOT / "universe" / "companies.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("retired:"):
            continue
        out.append(line)
    return out


def load_patterns() -> dict:
    return json.loads((ROOT / "universe" / "component_patterns.json").read_text())


def discover_npm(patterns: dict, budget: Budget, args) -> list[str]:
    names: set[str] = set()
    compiled = [re.compile(p) for p in patterns["npm_name_patterns"]]
    for q in patterns["npm_search_queries"]:
        frm = 0
        while frm < args.npm_search_depth:
            if budget.exhausted():
                return sorted(names)
            url = ("https://registry.npmjs.org/-/v1/search?text=%s&size=250&from=%d"
                   % (urllib.parse.quote(q), frm))
            r = fetch(url, args.timeout, args.max_body)
            budget.spend(len(r.get("body") or b""))
            if not r["ok"]:
                log("  npm search %-28s from=%-4d -> %s" % (q, frm, r.get("error")))
                break
            try:
                objs = json.loads(r["body"]).get("objects", [])
            except Exception:
                break
            if not objs:
                break
            for o in objs:
                n = (o.get("package") or {}).get("name")
                if n and any(c.match(n) for c in compiled):
                    names.add(n)
            frm += 250
            time.sleep(args.delay)
        log("  npm search %-28s -> %d matching names so far" % (q, len(names)))
    return sorted(names)


def discover_pypi(patterns: dict, budget: Budget, args) -> list[str]:
    """Names on PyPI matching the MCP patterns.

    The PyPI simple index is a ~48MB list of every project name on PyPI. It is
    discovery input only - never stored - but re-downloading it every day would
    spend a quarter of the byte budget on a file whose useful content barely
    moves. It is refreshed on an age check and the matching names are cached in
    the meantime, so a daily run spends its budget on packages instead.
    """
    compiled = [re.compile(p) for p in patterns["pypi_name_patterns"]]

    cached = None
    if PYPI_NAMES_PATH.exists():
        try:
            cached = json.loads(PYPI_NAMES_PATH.read_text())
            age_h = (dt.datetime.now(dt.timezone.utc)
                     - dt.datetime.fromisoformat(cached["refreshed_at"])).total_seconds() / 3600
            if age_h < args.pypi_index_max_age_hours:
                log("  pypi name cache %.1fh old (<%dh) -> reusing %d names"
                    % (age_h, args.pypi_index_max_age_hours, len(cached["names"])))
                return cached["names"]
        except Exception:
            cached = None

    r = fetch("https://pypi.org/simple/", args.timeout, args.pypi_index_max_bytes,
              accept="application/vnd.pypi.simple.v1+json")
    budget.spend(len(r.get("body") or b""))
    if not r["ok"]:
        log("  pypi simple index -> %s" % r.get("error"))
        return cached["names"] if cached else []
    if r.get("truncated"):
        log("  pypi simple index TRUNCATED at %d bytes - name set is incomplete"
            % args.pypi_index_max_bytes)
    try:
        projects = json.loads(r["body"]).get("projects", [])
    except Exception as e:
        log("  pypi simple index unparseable: %s" % e)
        return cached["names"] if cached else []

    names = sorted({p["name"] for p in projects
                    if p.get("name") and any(c.match(p["name"].lower()) for c in compiled)})
    log("  pypi simple index -> %d projects scanned, %d matching names"
        % (len(projects), len(names)))
    if not args.dry_run:
        STATE.mkdir(parents=True, exist_ok=True)
        PYPI_NAMES_PATH.write_text(json.dumps(
            {"refreshed_at": now_iso(), "projects_scanned": len(projects),
             "names": names}, indent=1))
    return names


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------

def extract_component_surface(doc: dict) -> dict:
    """Pull the declared surface out of a registry document. No inference."""
    versions = doc.get("versions") or {}
    latest_tag = (doc.get("dist-tags") or {}).get("latest")
    latest = versions.get(latest_tag) if isinstance(versions, dict) else None
    if not isinstance(latest, dict):
        latest = doc.get("info") if isinstance(doc.get("info"), dict) else {}

    surface = {k: latest[k] for k in MCP_SURFACE_KEYS if isinstance(latest, dict) and k in latest}
    for k in MCP_SURFACE_KEYS:
        if k in doc and k not in surface:
            surface[k] = doc[k]

    maintainers = doc.get("maintainers")
    if maintainers is None and isinstance(doc.get("info"), dict):
        maintainers = doc["info"].get("maintainer")

    return {
        "declared_mcp_surface": surface or None,
        "declared_tool_descriptions_present": bool(
            surface.get("tools") or surface.get("toolDescriptions")),
        "parameter_schemas_present": bool(
            json.dumps(surface).find("inputSchema") >= 0
            or json.dumps(surface).find("parameters") >= 0) if surface else False,
        "versions": sorted(versions.keys()) if isinstance(versions, dict) else
                    sorted((doc.get("releases") or {}).keys()),
        "latest_version": latest_tag or (doc.get("info") or {}).get("version"),
        "maintainers": maintainers,
    }


def capture_component(name: str, registry: str, store: Store, robots: Robots,
                      budget: Budget, args) -> dict | None:
    if budget.exhausted():
        return None
    if registry == "npm":
        url = "https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@")
    else:
        url = "https://pypi.org/pypi/%s/json" % urllib.parse.quote(name)

    allowed, why = robots.allowed(url)
    key = "component:%s:%s" % (registry, name)
    if not allowed:
        return store.note({"key": key, "universe": "components", "kind": registry + "-manifest",
                           "source_url": url, "fetched_at": now_iso(), "change": "skipped",
                           "skipped_because": "robots.txt disallows this path (%s)" % why})

    r = fetch(url, args.timeout, args.max_body)
    budget.spend(len(r.get("body") or b""))
    if not r["ok"]:
        return store.note({"key": key, "universe": "components", "kind": registry + "-manifest",
                           "source_url": url, "fetched_at": now_iso(),
                           "change": "absent" if r["status"] > 0 else "unreachable",
                           "http_status": r["status"], "error": r.get("error")})

    raw = r["body"]
    counter = [0]
    try:
        doc = json.loads(raw)
        surface = extract_component_surface(doc)
        stored_obj = {
            "_capture": "datumline-capture/0.1 - capture only, no assessment",
            "source_url": url, "registry": registry, "name": name,
            "manifest": redact_json(doc, counter),
        }
        stored_obj["declared"] = redact_json(surface, counter)
        stored = json.dumps(stored_obj, indent=1, sort_keys=True).encode()
        meta = {
            "http_status": r["status"],
            "content_type": r["content_type"],
            "emails_redacted": counter[0],
            "version_count": len(surface["versions"]),
            "latest_version": surface["latest_version"],
            "declared_tool_descriptions_present": surface["declared_tool_descriptions_present"],
            "parameter_schemas_present": surface["parameter_schemas_present"],
            "truncated": r["truncated"],
        }
    except Exception as e:
        text, n = redact_text(raw.decode("utf-8", "replace"))
        stored = text.encode()
        meta = {"http_status": r["status"], "content_type": r["content_type"],
                "emails_redacted": n, "parse_error": str(e)[:200], "truncated": r["truncated"]}

    return store.write(key, "components", registry + "-manifest", url, raw, stored, meta)


def capture_company(domain: str, store: Store, robots: Robots, budget: Budget,
                    args) -> list[dict]:
    out = []
    for kind, path in COMPANY_PATHS:
        if budget.exhausted():
            break
        url = "https://" + domain + path
        key = "company:%s:%s" % (domain, path)
        allowed, why = robots.allowed(url)
        if not allowed:
            out.append(store.note({"key": key, "universe": "companies", "kind": kind,
                                   "source_url": url, "fetched_at": now_iso(), "change": "skipped",
                                   "skipped_because": "robots.txt disallows this path (%s)" % why}))
            continue

        r = fetch(url, args.timeout, args.max_body)
        budget.spend(len(r.get("body") or b""))
        if not r["ok"]:
            # A 404 is a real observation about the domain: the file is not
            # published, and that is worth recording. A transport failure is NOT
            # that observation - it says nothing about what the domain serves, and
            # recording it as "absent" would put a false claim in the record and
            # then show a spurious change when the network recovers. The two are
            # kept apart.
            reachable = r["status"] > 0
            out.append(store.note({
                "key": key, "universe": "companies", "kind": kind,
                "source_url": url, "fetched_at": now_iso(),
                "change": "absent" if reachable else "unreachable",
                "http_status": r["status"], "error": r.get("error")}))
            continue

        raw = r["body"]
        if not raw.strip():
            out.append(store.note({"key": key, "universe": "companies", "kind": kind,
                                   "source_url": url, "fetched_at": now_iso(), "change": "absent",
                                   "http_status": r["status"], "error": "empty body"}))
            continue

        ctype = r["content_type"]
        if "html" in ctype:
            # A soft-404: the site served its app shell rather than the file.
            out.append(store.note({"key": key, "universe": "companies", "kind": kind,
                                   "source_url": url, "fetched_at": now_iso(), "change": "absent",
                                   "http_status": r["status"], "content_type": ctype,
                                   "error": "served HTML, not the requested file"}))
            continue

        text, n = redact_text(raw.decode("utf-8", "replace"))
        stored = text.encode()
        out.append(store.write(key, "companies", kind, url, raw, stored, {
            "http_status": r["status"], "content_type": ctype,
            "emails_redacted": n, "final_url": r["final_url"],
            "truncated": r["truncated"], "robots": why,
        }))
        time.sleep(args.delay)
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Datumline capture. Capture only.")
    ap.add_argument("--max-seconds", type=int, default=2700,
                    help="hard wall-clock stop (default 2700 = 45 minutes)")
    ap.add_argument("--max-bytes", type=int, default=200 * 1024 * 1024,
                    help="hard byte stop (default 200MB)")
    ap.add_argument("--max-body", type=int, default=8 * 1024 * 1024,
                    help="per-response ceiling")
    ap.add_argument("--pypi-index-max-bytes", type=int, default=64 * 1024 * 1024)
    ap.add_argument("--pypi-index-max-age-hours", type=int, default=168,
                    help="refresh the PyPI name cache when it is older than this")
    ap.add_argument("--npm-search-depth", type=int, default=1000)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--delay", type=float, default=0.15, help="politeness delay per request")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--universes", default="components,companies")
    ap.add_argument("--limit-components", type=int, default=0, help="0 = no limit")
    ap.add_argument("--limit-companies", type=int, default=0, help="0 = no limit")
    ap.add_argument("--dry-run", action="store_true",
                    help="discover and report, write nothing to the store")
    args = ap.parse_args()

    for d in (BODIES, DIFFS, INDEX, DAILY, STATE):
        d.mkdir(parents=True, exist_ok=True)

    budget = Budget(args.max_seconds, args.max_bytes)
    robots = Robots(args.timeout)
    store = Store()
    universes = {u.strip() for u in args.universes.split(",") if u.strip()}
    started = now_iso()
    first_run = not RECORDS_PATH.exists()

    log("datumline capture - CAPTURE ONLY, no scoring, no grading, no publishing")
    log("started %s  budget %ds / %d bytes  first_run=%s"
        % (started, args.max_seconds, args.max_bytes, first_run))

    counts = {"components_discovered": 0, "companies": 0, "records": 0,
              "skipped_by_robots": 0, "errors": 0}

    # COMPANIES RUNS FIRST, DELIBERATELY.
    # It is the perishable universe: /.well-known files are served live and
    # nobody archives them for us, so a day missed there is gone for good. The
    # component registries keep their own history and a package skipped today
    # is still there tomorrow. Companies is also the small universe - a few
    # thousand small files - so giving it the head of the budget costs the
    # component sweep very little.
    if "companies" in universes and not budget.exhausted():
        domains = load_companies()
        if args.limit_companies:
            domains = domains[:args.limit_companies]
        counts["companies"] = len(domains)
        log("COMPANIES: %d domains x %d public paths" % (len(domains), len(COMPANY_PATHS)))
        if not args.dry_run:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(capture_company, d, store, robots, budget, args): d
                        for d in domains}
                done = 0
                for f in as_completed(futs):
                    done += 1
                    try:
                        recs = f.result()
                    except Exception as e:
                        counts["errors"] += 1
                        log("  company error %s: %s" % (futs[f], e))
                        continue
                    for rec in recs:
                        counts["records"] += 1
                        ch = rec.get("change")
                        if ch == "skipped":
                            counts["skipped_by_robots"] += 1
                        elif ch == "absent":
                            counts["company_paths_absent"] = counts.get("company_paths_absent", 0) + 1
                        elif ch == "unreachable":
                            counts["company_paths_unreachable"] = counts.get("company_paths_unreachable", 0) + 1
                        else:
                            counts["company_paths_captured"] = counts.get("company_paths_captured", 0) + 1
                    if done % 50 == 0:
                        log("  companies %d/%d  (%.0fs, %.1fMB)"
                            % (done, len(domains), budget.elapsed(), budget.bytes / 1e6))

    if "components" in universes and not budget.exhausted():
        patterns = load_patterns()
        log("COMPONENTS: discovering")
        npm_names = discover_npm(patterns, budget, args)
        pypi_names = discover_pypi(patterns, budget, args)
        targets = [(n, "npm") for n in npm_names] + [(n, "pypi") for n in pypi_names]
        counts["components_universe"] = len(targets)

        # The component universe is far larger than one budgeted run can cover.
        # Starting from the top every day would capture the same alphabetical
        # prefix forever and never reach the tail. The cursor carries on from
        # where the last run stopped, so the sweep walks the whole universe over
        # successive runs instead of grinding the same names.
        cursor = 0
        if CURSOR_PATH.exists():
            try:
                cursor = int(json.loads(CURSOR_PATH.read_text()).get("components", 0))
            except Exception:
                cursor = 0
        if targets:
            cursor %= len(targets)
            targets = targets[cursor:] + targets[:cursor]
        if args.limit_components:
            targets = targets[:args.limit_components]
        counts["components_discovered"] = len(targets)
        counts["components_cursor_start"] = cursor
        log("COMPONENTS: %d npm + %d pypi = %d in universe; sweeping from cursor %d"
            % (len(npm_names), len(pypi_names), counts["components_universe"], cursor))

        attempted = 0
        if not args.dry_run:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(capture_component, n, reg, store, robots, budget, args): (n, reg)
                        for n, reg in targets}
                done = 0
                for f in as_completed(futs):
                    done += 1
                    try:
                        rec = f.result()
                    except Exception as e:
                        counts["errors"] += 1
                        log("  component error %s: %s" % (futs[f], e))
                        continue
                    if rec is None:
                        continue
                    attempted += 1
                    counts["records"] += 1
                    if rec.get("change") == "skipped":
                        counts["skipped_by_robots"] += 1
                    elif rec.get("change") in ("absent", "unreachable"):
                        counts["errors"] += 1
                    if done % 100 == 0:
                        log("  components %d/%d  (%.0fs, %.1fMB)"
                            % (done, len(targets), budget.elapsed(), budget.bytes / 1e6))

            if counts["components_universe"] and not args.limit_components:
                new_cursor = (cursor + attempted) % counts["components_universe"]
                CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
                CURSOR_PATH.write_text(json.dumps(
                    {"components": new_cursor, "updated_at": now_iso(),
                     "universe_size": counts["components_universe"],
                     "captured_this_run": attempted}, indent=1))
                counts["components_cursor_end"] = new_cursor
                log("COMPONENTS: captured %d, cursor %d -> %d of %d"
                    % (attempted, cursor, new_cursor, counts["components_universe"]))

    run = {
        "capture_version": "0.1",
        "purpose": "capture only - no scoring, grading, ranking or publication",
        "started_at": started,
        "finished_at": now_iso(),
        "elapsed_seconds": round(budget.elapsed(), 1),
        "bytes_fetched": budget.bytes,
        "budget_seconds": args.max_seconds,
        "budget_bytes": args.max_bytes,
        "first_run": first_run,
        "truncated": bool(budget.stopped_because),
        "truncated_because": budget.stopped_because,
        "universes": sorted(universes),
        "counts": counts,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    }

    if args.dry_run:
        log(json.dumps(run, indent=2))
        return 0

    run.update(store.flush(run))
    (STORE / "last_run.json").write_text(json.dumps(run, indent=2, sort_keys=True))

    log("-" * 70)
    log(json.dumps(run, indent=2, sort_keys=True))
    if budget.stopped_because:
        log("NOTE: run stopped early - %s. The record for this run is partial."
            % budget.stopped_because)
    return 0


if __name__ == "__main__":
    sys.exit(main())
