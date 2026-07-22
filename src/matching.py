"""
Identity resolution: identify records from different bureaus that belong to
the same applicant.

Matching is done in three steps, from strongest to weakest:

1. Exact PAN match:
   If two records have the same complete PAN, they are treated as the same
   applicant. Since PAN is unique, this is the strongest match. However,
   PAN may sometimes be missing or masked.

2. Masked PAN match:
   Some bureaus mask part of the PAN, for example "IJKPV****S".
   We compare the visible characters with a full PAN and treat '*' as a
   wildcard. If the visible characters match, the records are considered
   a likely match.

3. Name + DOB match:
   If PAN is not available, we compare normalized names along with an exact
   DOB match. Name matching is fuzzy to handle small spelling differences,
   such as "Sunita Reddy" and "Sunita Reddi".

Any records that still do not match are treated as applicants reported by
only one bureau.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher

from src.models import BureauRecord, UnifiedApplicant
from src.normalize import to_bureau_score

FUZZY_NAME_THRESHOLD = 0.82


def _normalized_name(r: BureauRecord) -> str:
    return f"{(r.first_name or '').strip().lower()} {(r.last_name or '').strip().lower()}".strip()


def _name_similarity(a: BureauRecord, b: BureauRecord) -> float:
    return SequenceMatcher(None, _normalized_name(a), _normalized_name(b)).ratio()


def _pan_matches_masked(masked: str, full: str) -> bool:
    if len(masked) != len(full):
        return False
    return all(m == "*" or m == f for m, f in zip(masked, full))


class _Group:

    def __init__(self, records, method, confidence):
        self.records = list(records)
        self.method = method
        self.confidence = confidence

    def add_masked(self, record, confidence=0.95):
        self.records.append(record)
        if self.method == "single_source":
            self.method = "pan_partial_masked"
            self.confidence = confidence
        elif self.method == "pan_exact":
            self.method = "pan_exact+masked_supplement"
        else:
            self.confidence = min(self.confidence, confidence)

    def add_fuzzy(self, record, similarity):
        self.records.append(record)
        if self.method == "single_source":
            self.method = "fuzzy_name_dob"
            self.confidence = similarity
        elif self.method in ("pan_exact", "pan_exact+masked_supplement"):
            self.method = self.method + "+fuzzy_supplement" if "fuzzy_supplement" not in self.method else self.method
            self.confidence = min(self.confidence, similarity)
        else:
            self.confidence = min(self.confidence, similarity)


def _group_by_clean_pan(records: list[BureauRecord]) -> tuple[list[_Group], list[BureauRecord], list[BureauRecord]]:
    """Returns (groups formed from clean/unmasked PANs, masked-pan leftovers,
    no-pan leftovers)."""
    by_pan: dict[str, list[BureauRecord]] = defaultdict(list)
    masked_leftover = []
    nopan_leftover = []
    for r in records:
        if r.is_clean_pan:
            by_pan[r.pan].append(r)
        elif r.is_masked_pan:
            masked_leftover.append(r)
        else:
            nopan_leftover.append(r)

    groups = []
    for pan, group in by_pan.items():
        method = "pan_exact" if len(group) > 1 else "single_source"
        groups.append(_Group(group, method, 1.0))
    return groups, masked_leftover, nopan_leftover


def _masked_pan_merge(groups: list[_Group], masked_records: list[BureauRecord]) -> list[BureauRecord]:
    still_unplaced = []
    for record in masked_records:
        placed = False
        for group in groups:
            clean_pans = {r.pan for r in group.records if r.is_clean_pan}
            if any(_pan_matches_masked(record.pan, p) for p in clean_pans):
                group.add_masked(record)
                placed = True
                break
        if not placed:
            still_unplaced.append(record)
    return still_unplaced


def _dob_conflicts(group: list[BureauRecord]) -> list[str]:
    dobs = {r.dob for r in group if r.dob is not None}
    if len(dobs) > 1:
        return [f"dob_conflict_across_{'_'.join(sorted(r.source_bureau for r in group))}"]
    return []


def _fuzzy_merge(groups: list[_Group], unassigned: list[BureauRecord]) -> list[_Group]:
    still_unassigned = []
    for record in unassigned:
        best_group = None
        best_score = 0.0
        for group in groups:
            for candidate in group.records:
                if candidate.dob is None or record.dob is None or candidate.dob != record.dob:
                    continue
                score = _name_similarity(record, candidate)
                if score > best_score:
                    best_score = score
                    best_group = group
        if best_group is not None and best_score >= FUZZY_NAME_THRESHOLD:
            best_group.add_fuzzy(record, round(best_score, 2))
        else:
            still_unassigned.append(record)

    for record in still_unassigned:
        groups.append(_Group([record], "single_source", 1.0))
    return groups


def _most_complete(group: list[BureauRecord]) -> BureauRecord:
    return min(group, key=lambda r: len(r.missing_fields()))


def _canonical_pan(group: list[BureauRecord]) -> str | None:
    """Prefer a clean PAN over a masked one over None."""
    clean = next((r.pan for r in group if r.is_clean_pan), None)
    if clean:
        return clean
    return next((r.pan for r in group if r.pan), None)


def _applicant_id(group: list[BureauRecord]) -> str:
    """Deterministic id so re-running the pipeline on the same input produces
    the same ids (important for idempotent re-runs / diffing across runs)."""
    pan = _canonical_pan(group)
    if pan:
        key = pan
    else:
        names = sorted({_normalized_name(r) for r in group})
        key = "|".join(names)
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def resolve_identities(records: list[BureauRecord]) -> list[UnifiedApplicant]:
    groups, masked_leftover, nopan_leftover = _group_by_clean_pan(records)
    still_unassigned = _masked_pan_merge(groups, masked_leftover)
    still_unassigned += nopan_leftover
    groups = _fuzzy_merge(groups, still_unassigned)

    unified = []
    for g in groups:
        recs = g.records
        anchor = _most_complete(recs)
        sources = sorted({r.source_bureau for r in recs})

        flags = []
        for r in recs:
            for m in r.missing_fields():
                flags.append(f"{r.source_bureau}_missing_{m}")
        flags.extend(_dob_conflicts(recs))

        unified.append(
            UnifiedApplicant(
                applicant_id=_applicant_id(recs),
                full_name=anchor.full_name,
                dob=next((r.dob for r in recs if r.dob), None),
                pan=_canonical_pan(recs),
                address=anchor.address,
                bureau_scores=[to_bureau_score(r) for r in recs],
                sources=sources,
                match_method=g.method,
                match_confidence=g.confidence,
                data_quality_flags=flags,
            )
        )
    return unified
