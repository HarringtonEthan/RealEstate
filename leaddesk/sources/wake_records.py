"""Wake County parcel/tax records + City of Raleigh building-permit records.

Both are public government data, free to query, no authentication. This
module only reads — it never writes anything back to the county.

Field names are configured in leaddesk/config.py (WAKE_PARCEL_FIELDS,
RALEIGH_PERMIT_FIELDS) since the exact schema is confirmed by
scripts/probe_records.py rather than guessed here.
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .. import config

UA = {"User-Agent": "leaddesk/0.1 (personal real-estate research tool; low volume)"}


def _arcgis_query(base_url: str, where: str, out_fields: str = "*", n: int = 50) -> list[dict]:
    """Query an ArcGIS FeatureServer/MapServer layer. Returns raw attribute dicts."""
    params = {
        "where": where,
        "outFields": out_fields,
        "resultRecordCount": n,
        "f": "json",
    }
    url = f"{base_url}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error'].get('message', data['error'])}")
    return [f.get("attributes", {}) for f in data.get("features", [])]


def _map_fields(raw: dict, field_map: dict) -> dict:
    return {key: raw.get(arcgis_name) for key, arcgis_name in field_map.items()}


def fetch_recent_renovation_permits() -> list[dict]:
    """Recent, substantial renovation permits from City of Raleigh open data."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.RENOVATION_LOOKBACK_DAYS))
    cutoff_ms = int(cutoff.timestamp() * 1000)
    date_field = config.RALEIGH_PERMIT_FIELDS["final_date"]
    desc_field = config.RALEIGH_PERMIT_FIELDS["description"]
    value_field = config.RALEIGH_PERMIT_FIELDS["valuation"]

    keyword_clause = " OR ".join(
        f"UPPER({desc_field}) LIKE '%{kw.upper()}%'" for kw in config.RENOVATION_KEYWORDS
    )
    where = (
        f"{date_field} >= {cutoff_ms} AND {value_field} >= {config.RENOVATION_MIN_VALUE} "
        f"AND ({keyword_clause})"
    )

    raw = _arcgis_query(config.RALEIGH_PERMITS_URL, where, n=100)
    return [_map_fields(r, config.RALEIGH_PERMIT_FIELDS) for r in raw]


def fetch_parcel_by_address(address: str) -> dict | None:
    """Look up owner/tax record for one situs address."""
    if not address:
        return None
    situs_field = config.WAKE_PARCEL_FIELDS["situs_address"]
    safe = address.replace("'", "''").upper()
    where = f"UPPER({situs_field}) LIKE '%{safe}%'"
    raw = _arcgis_query(config.WAKE_PARCELS_URL, where, n=1)
    if not raw:
        return None
    return _map_fields(raw[0], config.WAKE_PARCEL_FIELDS)


def find_renovation_candidates() -> list[dict]:
    """Cross-reference recent permits with ownership records.

    Returns a list of merged candidate dicts (permit + parcel fields), or a
    single-item list with an "_error" key if the permit fetch itself fails
    (network unreachable, endpoint down, schema mismatch) — same convention
    as leaddesk.sources.reddit, so callers handle both sources identically.
    """
    try:
        permits = fetch_recent_renovation_permits()
    except Exception as exc:
        return [{"_error": f"wake_records: could not fetch permits ({exc})"}]

    candidates = []
    for permit in permits:
        address = permit.get("address")
        try:
            parcel = fetch_parcel_by_address(address)
        except Exception:
            continue  # one bad address lookup shouldn't sink the whole scan
        if not parcel or not parcel.get("pin"):
            continue
        candidates.append({**permit, **parcel})
    return candidates
