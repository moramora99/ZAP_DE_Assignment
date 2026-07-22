"""
Parser for Bureau Alpha: reads CSV data with credit scores ranging from
300-900, ISO date format, Indian address fields, and PAN as the identity field.

DOB can sometimes be missing. If it is blank, it is stored as None.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.models import Address, BureauRecord

SCORE_SCALE = "CIBIL-like 300-900 (higher = lower risk)"


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse(path: str | Path) -> list[BureauRecord]:
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(
                BureauRecord(
                    source_bureau="alpha",
                    first_name=row["first_name"].strip() or None,
                    last_name=row["last_name"].strip() or None,
                    dob=_parse_date(row["dob"]),
                    pan=row["pan"].strip() or None,
                    address=Address(
                        street=row["street"].strip() or None,
                        city=row["city"].strip() or None,
                        state=row["state"].strip() or None,
                        pincode=row["pincode"].strip() or None,
                    ),
                    raw_score=float(row["cibil_score"]) if row["cibil_score"].strip() else None,
                    score_scale=SCORE_SCALE,
                    report_date=_parse_date(row["report_date"]),
                )
            )
    return records
