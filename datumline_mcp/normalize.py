"""CANDIDATE layer-score derivation - NOT LOCKED METHODOLOGY.
Fills the stage that did not exist: harvest -> [normalize] -> score -> grade.
Every mapping is a proposal for the v0.3 red-pen. Scale 1.0 best to 5.0 worst.
"""
from __future__ import annotations
import datetime as dt
from typing import Any

def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (dt.datetime.now(dt.timezone.utc)
                - dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    except ValueError:
        return None

def _band(value, thresholds, default: float = 3.0) -> float:
    if value is None:
        return default
    for limit, score in thresholds:
        if value <= limit:
            return score
    return thresholds[-1][1]

def derive(payload: dict[str, Any]) -> dict[str, Any]:
    times = payload.get("time", {}) or {}
    versions = [k for k in times if k not in ("created", "modified")]
    maintainers = payload.get("maintainers", []) or []
    latest_tag = (payload.get("dist-tags", {}) or {}).get("latest")
    latest = (payload.get("versions", {}) or {}).get(latest_tag, {}) or {}

    age_days = _days_since(times.get("created"))
    idle_days = _days_since(times.get("modified"))
    releases = len(versions)
    deps = len(latest.get("dependencies", {}) or {})
    has_repo = bool(payload.get("repository"))
    has_license = bool(payload.get("license") or latest.get("license"))
    has_bugs = bool(payload.get("bugs"))
    deprecated = bool(latest.get("deprecated"))
    rpy = (releases / max(age_days, 1)) * 365 if age_days else None

    obs = {"age_days": age_days, "idle_days": idle_days, "releases": releases,
           "maintainers": len(maintainers), "dependencies": deps,
           "has_repository": has_repo, "has_license": has_license,
           "has_bugs_url": has_bugs, "deprecated": deprecated,
           "releases_per_year": round(rpy, 2) if rpy else None}

    provenance = 1.0
    if not has_repo:
        provenance += 2.0
    if not has_license:
        provenance += 1.5
    if len(maintainers) == 0:
        provenance += 1.0
    provenance = min(5.0, provenance)

    mutation = _band(rpy, [(4, 1.5), (12, 2.0), (26, 3.0), (52, 4.0), (999, 5.0)])

    conduct = 2.0
    if not has_bugs:
        conduct += 1.5
    if deprecated:
        conduct = 5.0
    conduct = min(5.0, conduct)

    implementation = _band(float(deps), [(0, 1.0), (5, 2.0), (15, 3.0), (30, 4.0), (999, 5.0)])

    stewardship = _band(float(idle_days) if idle_days is not None else None,
                        [(30, 1.5), (90, 2.0), (180, 3.0), (365, 4.0), (99999, 5.0)])
    if len(maintainers) == 1:
        stewardship = min(5.0, stewardship + 0.5)
    if len(maintainers) == 0:
        stewardship = 5.0

    flags = {"anonymous_maintainer": len(maintainers) == 0,
             "maintainer_transfer_under_90d": False,
             "unauthenticated_remote_endpoint": False,
             "critical_cve_unremediated": False,
             "tool_description_injection_detected": False}

    return {"layer_scores": {"provenance": round(provenance, 2),
                             "mutation": round(mutation, 2),
                             "conduct": round(conduct, 2),
                             "implementation": round(implementation, 2),
                             "stewardship": round(stewardship, 2)},
            "flags": flags, "observations": obs,
            "releases": releases, "registry_age_days": age_days or 0}
