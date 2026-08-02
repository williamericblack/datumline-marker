from __future__ import annotations
from dataclasses import dataclass

LAYERS = ("provenance", "mutation", "conduct", "implementation", "stewardship")

WEIGHT_VECTORS = {
    "W-A": {"label": "x402-inherited control",
            "weights": {"provenance": 20, "mutation": 25, "conduct": 20,
                        "implementation": 15, "stewardship": 20}},
    "W-B": {"label": "incident-informed",
            "weights": {"provenance": 20, "mutation": 10, "conduct": 20,
                        "implementation": 25, "stewardship": 25}},
    "W-C": {"label": "clean-sheet locked v0.3",
            "weights": {"provenance": 25, "mutation": 25, "conduct": 15,
                        "implementation": 25, "stewardship": 10}},
}

HARD_CAPS = {
    "maintainer_transfer_under_90d": 4,
    "tool_description_injection_detected": 5,
    "unauthenticated_remote_endpoint": 3,
    "critical_cve_unremediated": 4,
    "anonymous_maintainer": 3,
}

@dataclass(frozen=True)
class GradeBand:
    maximum: float
    grade: str

GRADE_BANDS = (GradeBand(1.5, "DL-1"), GradeBand(2.5, "DL-2"), GradeBand(3.5, "DL-3"),
               GradeBand(4.5, "DL-4"), GradeBand(5.0, "DL-5"))

def grade_from_score(score: float) -> str:
    bounded = max(1.0, min(5.0, float(score)))
    for band in GRADE_BANDS:
        if bounded <= band.maximum:
            return band.grade
    return "DL-5"
