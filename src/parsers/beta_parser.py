"""
Parser for Bureau Beta: reads JSON data with nested Indian address fields,
risk scores from 0-100, and dates in MM/DD/YYYY format.

Quirks handled:

* full_name is provided as a single string, so it is split into first and
  last name as accurately as possible.
* PAN can be missing or partially masked with '*' characters. Both cases are
  kept as-is and handled later during identity matching.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.models import Address, BureauRecord

SCORE_SCALE = "Risk score 0-100 (higher = lower risk)"


def _parse_date(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").date()


def _parse_report_date(value: str):
    if not value:
        return None
    return datetime.strptime(value.split("T")[0], "%Y-%m-%d").date()


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.replace(".", "").split()
    if len(parts) == 1:
        return parts[0], ""
    first = parts[0]
    last = parts[-1]
    return first, last


def parse(path: str | Path) -> list[BureauRecord]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    records = []
    for row in payload["records"]:
        first, last = _split_name(row["full_name"])
        addr = row.get("address") or {}
        records.append(
            BureauRecord(
                source_bureau="beta",
                first_name=first or None,
                last_name=last or None,
                dob=_parse_date(row.get("birth_date")),
                pan=row.get("pan") or None,
                address=Address(
                    street=addr.get("street"),
                    city=addr.get("city"),
                    state=addr.get("state"),
                    pincode=addr.get("pincode"),
                ),
                raw_score=float(row["risk_score"]) if row.get("risk_score") is not None else None,
                score_scale=SCORE_SCALE,
                report_date=_parse_report_date(row.get("pulled_at")),
            )
        )
    return records
