"""
Parser for Bureau Gamma: reads legacy pipe-delimited data.

Format: NAME|DOB|PAN|ADDR|SCORE|SCOREDATE

* NAME is stored as "LAST, FIRST" in uppercase.
* DOB and score date use YYYYMMDD format.
* Address is stored as a single string and is split into address, city, state,
  and 6-digit pincode where possible.
* Scores range from 1-999 and use the opposite direction from Alpha and Beta,
  where a lower score means lower risk.
* PAN can be missing and is stored as None when not available.

Address parsing uses best-effort matching and may not handle every possible
address format. This limitation is also noted in the README.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from src.models import Address, BureauRecord

SCORE_SCALE = "Legacy index 1-999 (LOWER = lower risk -- inverted vs. Alpha/Beta)"

_ADDR_RE = re.compile(r"^(?P<street>.+),\s*(?P<city>.+),\s*(?P<state>.+)\s+(?P<pincode>\d{6})$")


def _parse_date(value: str):
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def _parse_name(raw: str) -> tuple[str, str]:
    if "," in raw:
        last, first = raw.split(",", 1)
        return first.strip().title(), last.strip().title()
    return raw.strip().title(), ""


def _parse_address(raw: str) -> Address:
    m = _ADDR_RE.match(raw.strip())
    if not m:
        return Address(street=raw.strip())
    return Address(
        street=m.group("street").strip(),
        city=m.group("city").strip(),
        state=m.group("state").strip(),
        pincode=m.group("pincode"),
    )


def parse(path: str | Path) -> list[BureauRecord]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, dob, pan, addr, score, score_date = line.split("|")
            first, last = _parse_name(name)
            records.append(
                BureauRecord(
                    source_bureau="gamma",
                    first_name=first or None,
                    last_name=last or None,
                    dob=_parse_date(dob),
                    pan=pan.strip() or None,
                    address=_parse_address(addr),
                    raw_score=float(score) if score.strip() else None,
                    score_scale=SCORE_SCALE,
                    report_date=_parse_date(score_date),
                )
            )
    return records
