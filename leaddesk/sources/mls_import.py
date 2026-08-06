"""MLS export ingestion — expired & withdrawn listings.

Diane exports these herself from her MLS (Matrix) and drops the CSV file in
MLS_IMPORT_DIR. This module NEVER logs into any MLS system — it only reads a
file that already exists on disk. See mls_export_template.csv at the repo
root for the expected shape.

Column names vary by MLS/export settings, so headers are matched flexibly
against a list of common aliases per field rather than an exact schema. If a
required field can't be found, the file is skipped with a clear warning
listing the headers that WERE found — send that to fix the mapping.
"""

import csv
import re

from .. import config

# canonical_field -> list of header aliases to match (case/space/punct-insensitive)
FIELD_ALIASES = {
    "mls_number": ["mlsnumber", "mls", "mlsid", "listingid"],
    "address": ["address", "streetaddress", "listingaddress", "propertyaddress"],
    "city": ["city"],
    "state": ["state", "stateorprovince"],
    "zip": ["zip", "zipcode", "postalcode"],
    "status": ["status", "mlsstatus", "listingstatus"],
    "list_price": ["listprice", "currentprice", "price"],
    "original_list_price": ["originallistprice", "origlistprice", "originalprice"],
    "list_date": ["listdate", "listingdate"],
    "off_market_date": ["offmarketdate", "expirationdate", "statuschangedate",
                         "withdrawndate", "expdate"],
    "dom": ["dom", "daysonmarket", "cumulativedom", "cdom"],
    "beds": ["beds", "bedrooms", "br"],
    "baths": ["baths", "bathrooms", "ba", "fullbaths"],
    "sqft": ["sqft", "squarefeet", "totalsqft", "livingarea"],
    "year_built": ["yearbuilt", "yrbuilt"],
    "list_agent": ["listagent", "listingagent", "agentname"],
    "list_office": ["listoffice", "listingoffice", "office"],
}


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _build_column_map(headers: list[str]) -> dict:
    """Returns {canonical_field: actual_csv_header} for every field we can match."""
    normalized = {_normalize(h): h for h in headers}
    mapping = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field] = normalized[alias]
                break
    return mapping


def find_export_files() -> list:
    config.MLS_IMPORT_DIR.mkdir(exist_ok=True)
    return sorted(p for p in config.MLS_IMPORT_DIR.glob("*.csv"))


def parse_export(path) -> tuple[list[dict], list[str]]:
    """Returns (rows, warnings). Each row is a dict of canonical field -> value."""
    warnings = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return [], [f"{path.name}: file has no header row, skipped"]
        colmap = _build_column_map(reader.fieldnames)

        required = ["address", "status"]
        missing = [f for f in required if f not in colmap]
        if missing:
            warnings.append(
                f"{path.name}: couldn't find required column(s) {missing}. "
                f"Headers found in the file: {reader.fieldnames}. "
                f"Send this list so the column mapping can be corrected."
            )
            return [], warnings

        rows = []
        for raw_row in reader:
            row = {field: raw_row.get(col) for field, col in colmap.items()}
            row["_source_file"] = path.name
            rows.append(row)
        return rows, warnings


def find_expired_withdrawn() -> tuple[list[dict], list[str]]:
    """All expired/withdrawn rows across every export file in the import dir."""
    files = find_export_files()
    if not files:
        return [], [f"No MLS export files found in {config.MLS_IMPORT_DIR} — "
                    "drop a CSV there (see mls_export_template.csv for the expected shape)."]

    all_rows, all_warnings = [], []
    for path in files:
        rows, warnings = parse_export(path)
        all_warnings.extend(warnings)
        for row in rows:
            status = (row.get("status") or "").strip().lower()
            if "expired" in status or "withdrawn" in status:
                all_rows.append(row)
    return all_rows, all_warnings
