from __future__ import annotations

import csv
import json
from pathlib import Path

from src.matching import resolve_identities
from src.models import UnifiedApplicant
from src.parsers import alpha_parser, beta_parser, gamma_parser

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

BUREAUS = ["alpha", "beta", "gamma"]


def load_all_records():
    alpha = alpha_parser.parse(DATA_DIR / "bureau_alpha.csv")
    beta = beta_parser.parse(DATA_DIR / "bureau_beta.json")
    gamma = gamma_parser.parse(DATA_DIR / "bureau_gamma.txt")
    return {"alpha": alpha, "beta": beta, "gamma": gamma}


def build_reconciliation_summary(by_bureau: dict, unified: list[UnifiedApplicant]) -> dict:
    total_in = sum(len(v) for v in by_bureau.values())
    matched_multi = [u for u in unified if len(u.sources) > 1]
    single_source = [u for u in unified if len(u.sources) == 1]
    incomplete = [u for u in unified if u.data_quality_flags]

    by_method = {}
    for u in unified:
        by_method[u.match_method] = by_method.get(u.match_method, 0) + 1

    return {
        "records_ingested": {b: len(v) for b, v in by_bureau.items()} | {"total": total_in},
        "unified_applicants": len(unified),
        "matched_across_multiple_bureaus": len(matched_multi),
        "single_bureau_only": len(single_source),
        "flagged_incomplete_or_conflicting": len(incomplete),
        "match_method_breakdown": by_method,
        "incomplete_applicant_ids": [u.applicant_id for u in incomplete],
    }


def _flatten_for_csv(u: UnifiedApplicant) -> dict:
    row = {
        "applicant_id": u.applicant_id,
        "full_name": u.full_name,
        "dob": u.dob.isoformat() if u.dob else "",
        "pan": u.pan or "",
        "street": u.address.street or "",
        "city": u.address.city or "",
        "state": u.address.state or "",
        "pincode": u.address.pincode or "",
        "sources": ";".join(u.sources),
        "match_method": u.match_method,
        "match_confidence": u.match_confidence,
        "blended_score": u.blended_score if u.blended_score is not None else "",
        "data_quality_flags": ";".join(u.data_quality_flags),
    }
    scores_by_bureau = {s.source_bureau: s for s in u.bureau_scores}
    for bureau in BUREAUS:
        s = scores_by_bureau.get(bureau)
        row[f"{bureau}_raw_score"] = s.raw_score if s else ""
        row[f"{bureau}_normalized_score"] = s.normalized_score if s else ""
    return row


def run(write_output: bool = True) -> tuple[list[UnifiedApplicant], dict]:
    by_bureau = load_all_records()
    all_records = [r for recs in by_bureau.values() for r in recs]
    unified = resolve_identities(all_records)
    summary = build_reconciliation_summary(by_bureau, unified)

    if write_output:
        OUTPUT_DIR.mkdir(exist_ok=True)
        rows = [_flatten_for_csv(u) for u in unified]
        with open(OUTPUT_DIR / "unified_applicants.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with open(OUTPUT_DIR / "reconciliation_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

    return unified, summary


if __name__ == "__main__":
    unified, summary = run()
    print(json.dumps(summary, indent=2))
