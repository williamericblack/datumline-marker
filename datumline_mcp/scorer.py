from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from .model import HARD_CAPS, LAYERS, WEIGHT_VECTORS, grade_from_score

@dataclass(frozen=True)
class ScoreInput:
    entity_id: str
    releases: int
    registry_age_days: int
    layer_scores: dict
    evidence: list = field(default_factory=list)
    flags: dict = field(default_factory=dict)

    @property
    def not_rated_reason(self):
        if self.releases < 3:
            return "NR: fewer than 3 published releases"
        if self.registry_age_days < 90:
            return "NR: fewer than 90 days registry history"
        return None

def _weighted_score(layer_scores: dict, weights: dict) -> float:
    missing = [l for l in LAYERS if l not in layer_scores]
    if missing:
        raise ValueError(f"missing layer scores: {', '.join(missing)}")
    total = sum(weights.values())
    return sum(float(layer_scores[l]) * weights[l] for l in LAYERS) / total

def _apply_caps(score: float, flags: dict):
    applied, capped = [], score
    for flag, cap in HARD_CAPS.items():
        if flags.get(flag) and capped < cap:
            capped = float(cap)
            applied.append(flag)
    return min(5.0, max(1.0, capped)), applied

def score_record(record: ScoreInput) -> dict:
    nr = record.not_rated_reason
    if nr:
        return {"entity_id": record.entity_id, "status": "NR",
                "reason": nr, "evidence": record.evidence}
    vectors = {}
    for vid, config in WEIGHT_VECTORS.items():
        raw = _weighted_score(record.layer_scores, config["weights"])
        capped, applied = _apply_caps(raw, record.flags)
        vectors[vid] = {"label": config["label"], "raw_score": round(raw, 3),
                        "capped_score": round(capped, 3),
                        "grade": grade_from_score(capped), "applied_caps": applied}
    return {"entity_id": record.entity_id, "status": "RATED",
            "layer_scores": record.layer_scores, "vectors": vectors,
            "evidence": record.evidence}
