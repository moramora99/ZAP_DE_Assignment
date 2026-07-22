"""
Common schema definitions.

We use two main schemas:

1. BureauRecord:
   This is the common format that every bureau parser produces, regardless
   of the source file format. Once the data is converted into this format,
   the same matching, scoring, and reconciliation logic can be used for all
   bureaus.

   If a new bureau is added, we only need to create a parser that converts
   its data into this format. The rest of the processing remains unchanged.

2. UnifiedApplicant:
   This is the final record created after identity matching. One applicant
   can have records from one or more bureaus.

Both the original bureau score and normalized score are kept. The normalized
score allows scores from different bureaus to be compared, while the original
score is useful for tracing the result back to the source data.

PAN (Permanent Account Number) is used as the main identity field for matching
applicants across bureaus. A complete PAN is generally a strong identifier,
but it may sometimes be missing or partially masked for privacy.

For example, a PAN may appear as "ABCPV****S". Because of this, the `pan`
field can contain '*' characters for masked values, or be empty when PAN is
not available. The masked PAN matching logic is handled in `matching.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Address:
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


@dataclass
class BureauRecord:
    source_bureau: str                  # e.g. "alpha", "beta", "gamma"
    first_name: Optional[str]
    last_name: Optional[str]
    dob: Optional[date]                 # None if the source omitted/blank it
    pan: Optional[str]                  # None if omitted; may contain '*' if masked
    address: Address
    raw_score: Optional[float]
    score_scale: str                    # human-readable description of the source's scale
    report_date: Optional[date]

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts)

    @property
    def is_clean_pan(self) -> bool:
        return bool(self.pan) and "*" not in self.pan

    @property
    def is_masked_pan(self) -> bool:
        return bool(self.pan) and "*" in self.pan

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.first_name or not self.last_name:
            missing.append("name")
        if not self.dob:
            missing.append("dob")
        if not self.pan:
            missing.append("pan")
        if not self.raw_score and self.raw_score != 0:
            missing.append("score")
        return missing


@dataclass
class BureauScore:
    source_bureau: str
    raw_score: Optional[float]
    score_scale: str
    normalized_score: Optional[float]   # 0-100, higher = lower credit risk
    report_date: Optional[date]


@dataclass
class UnifiedApplicant:
    applicant_id: str                   # stable synthetic id, derived from match key
    full_name: str                      # from the most complete contributing record
    dob: Optional[date]
    pan: Optional[str]                  # prefers a clean (unmasked) PAN if any record has one
    address: Address = field(default_factory=Address)   # from the most complete contributing record
    bureau_scores: list[BureauScore] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)          # which bureaus contributed
    match_method: str = "unmatched"
    match_confidence: float = 1.0
    data_quality_flags: list[str] = field(default_factory=list)

    @property
    def blended_score(self) -> Optional[float]:
        vals = [s.normalized_score for s in self.bureau_scores if s.normalized_score is not None]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 1)
