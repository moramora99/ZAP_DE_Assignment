# Common Credit Profile from Multiple Bureau Sources

This project combines credit bureau data from three different sources
into one unified applicant profile.

Since this project uses Indian data, PAN (Permanent Account Number) is
used as the main identity field to match applicants across bureaus.

## Quick Start

``` bash
cd credit_profile
python3 -m src.pipeline
```

This creates two files in the `output/` folder:

-   `unified_applicants.csv` --- final combined dataset with one row per
    applicant
-   `reconciliation_summary.json` --- summary of input records, matched
    records, and incomplete records

## The Three Bureaus

  -----------------------------------------------------------------------
  Bureau            Format            Score Scale       Key Differences
  ----------------- ----------------- ----------------- -----------------
  Alpha             CSV               300-900, higher = DOB can be blank
                                      better            

  Beta              JSON              0-100, higher =   Nested address,
                                      better            full name in one
                                                        field, name
                                                        variations, PAN
                                                        can be missing or
                                                        masked, and dates
                                                        use `MM/DD/YYYY`

  Gamma             Pipe-delimited    1-999, lower =    `"LAST, FIRST"`
                    text              better            name format,
                                                        `YYYYMMDD` dates,
                                                        and address
                                                        stored as one
                                                        string
  -----------------------------------------------------------------------

The `data/` folder contains 16 records for 8 applicants.

-   5 applicants appear in two or more bureaus to test matching.
-   3 applicants appear in only one bureau to test unmatched records.
-   The data also includes cases such as missing or masked PANs,
    spelling differences in names, missing DOBs, and PAN/DOB mismatches.

## Architecture

``` text
parsers/{alpha,beta,gamma}_parser.py
                ↓
          BureauRecord
                ↓
           matching.py
                ↓
          normalize.py
                ↓
       UnifiedApplicant
```

Each parser reads its bureau's file format and converts the data into a
common `BureauRecord` format.

After that, the same matching, score normalization, and reconciliation
logic is used for all bureaus.

## Schema Design

### Two Main Schemas

`BureauRecord` is the common format produced by each parser.

`UnifiedApplicant` is the final combined record created after matching
applicants across bureaus.

Keeping these separate makes it easier to add another bureau later. We
only need to create a new parser, while most of the existing logic
remains unchanged.

### Raw and Normalized Scores

Both the original bureau score and the normalized score are kept.

The normalized score makes scores from different bureaus easier to
compare, while the original score helps trace results back to the source
data for auditing.

### Identity Matching

Applicants are matched in three steps:

1.  **Exact PAN match** --- If records have the same complete PAN, they
    are treated as the same applicant. This is the strongest matching
    method.
2.  **Masked PAN match** --- Some bureaus may mask part of the PAN, for
    example `"IJKPV****S"`. The visible characters are compared with
    full PANs, while `*` is treated as a wildcard.
3.  **Name + DOB match** --- If PAN is not available, normalized names
    are compared along with an exact DOB match. Fuzzy name matching
    helps handle small spelling differences.

### Score Normalization

Each bureau uses a different score range, and Gamma's scoring direction
is opposite to Alpha and Beta.

Alpha and Beta use higher scores for lower risk, while Gamma uses lower
scores for lower risk.

All scores are converted to a common 0-100 scale where a higher
normalized score always means lower risk.

This makes scores easier to compare across bureaus.

### Match Method Tracking

The method used to match each applicant is recorded while the records
are being matched.

This is more accurate than deciding the match method after records have
already been grouped.

For example, a record matched using name and DOB should remain marked as
a fuzzy match even if another record in the same group contains a PAN.

## Adding a Fourth Bureau

1.  Create `parsers/<name>_parser.py` with a
    `parse(path) -> list[BureauRecord]` function.
2.  Add the bureau's score range and direction to `_BUREAU_RANGES` in
    `normalize.py`.
3.  Add the new file to `load_all_records()` in `pipeline.py`.
4.  The existing matching, scoring, and reconciliation logic can remain
    unchanged.
5.  If the bureau uses masked PAN values, make sure the masking format
    is handled correctly.

## Current Limitations

### Blended Score

`blended_score` currently calculates a simple average of the normalized
scores from all available bureaus.

This assumes that all bureau scores are equally reliable, which may not
always be true.

A better approach could consider factors such as score recency and data
completeness. Another option would be to provide the individual bureau
scores and allow the consuming system or risk model to decide how they
should be combined.

### Masked PAN Matching

Masked PAN matching uses the visible characters of a partially hidden
PAN to find possible matches.

This works well for this small dataset, but with a much larger
real-world dataset, multiple applicants could potentially have similar
masked PAN values.

A production system could reduce this risk by using additional
information, such as name or DOB, to confirm masked PAN matches.
