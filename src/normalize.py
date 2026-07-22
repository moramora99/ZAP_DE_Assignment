"""
Score normalization: convert each bureau's raw score to a common 0-100 scale,
where a higher score always means lower credit risk.

Each bureau uses a different scoring range, and Gamma's scoring direction is
opposite to the other two. Normalizing both the range and direction makes the
scores easier to compare across bureaus.

Scores are normalized using min-max scaling based on each bureau's defined
score range. This provides a common scale for comparison, but it does not mean
the scores represent exactly the same level of risk, since each bureau may use
a different scoring model. See the README for more details.
"""
from __future__ import annotations

from src.models import BureauRecord, BureauScore

# (min, max, higher_is_better)
_BUREAU_RANGES = {
    "alpha": (300, 900, True),
    "beta": (0, 100, True),
    "gamma": (1, 999, False),
}


def normalize_score(source_bureau: str, raw_score: float | None) -> float | None:
    if raw_score is None:
        return None
    lo, hi, higher_is_better = _BUREAU_RANGES[source_bureau]
    pct = (raw_score - lo) / (hi - lo)
    if not higher_is_better:
        pct = 1 - pct
    pct = max(0.0, min(1.0, pct))
    return round(pct * 100, 1)


def to_bureau_score(record: BureauRecord) -> BureauScore:
    return BureauScore(
        source_bureau=record.source_bureau,
        raw_score=record.raw_score,
        score_scale=record.score_scale,
        normalized_score=normalize_score(record.source_bureau, record.raw_score),
        report_date=record.report_date,
    )
