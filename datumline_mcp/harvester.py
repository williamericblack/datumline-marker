from __future__ import annotations
import hashlib, json, urllib.error, urllib.parse, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

USER_AGENT = "Datumline-MCP-v1/0.1 (zero-spend; public APIs only)"

@dataclass(frozen=True)
class EvidenceRecord:
    source_url: str
    retrieved_at: str
    as_of_date: str | None
    artifact_hash: str
    coverage_gap: str
    backtest_eligible: bool
    payload: dict[str, Any]

def artifact_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def fetch_json(url: str, *, timeout: int = 20) -> EvidenceRecord:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"free-source fetch failed for {url}: {exc}") from exc
    return EvidenceRecord(source_url=url,
                          retrieved_at=datetime.now(timezone.utc).isoformat(),
                          as_of_date=None, artifact_hash=artifact_hash(body),
                          coverage_gap="PARTIAL", backtest_eligible=True,
                          payload=json.loads(body.decode("utf-8")))

def npm_package(package_name: str) -> EvidenceRecord:
    return fetch_json(f"https://registry.npmjs.org/{urllib.parse.quote(package_name, safe='@/')}")

def to_jsonable(record: EvidenceRecord) -> dict[str, Any]:
    return asdict(record)
