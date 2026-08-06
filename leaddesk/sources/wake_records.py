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
    """Recent, substantial renovation permits from City of Raleigh open data.

    The owner-of-record's name and mailing address ride along on every permit
    row already (parcelownername / parcelowneraddress1), so this one query is
    enough to compute the absentee-owner signal — no parcel join required for
    that part.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.RENOVATION_LOOKBACK_DAYS))
    # This ArcGIS service rejects epoch-millisecond integers for Date-field
    # comparisons ("Cannot perform query. Invalid query parameters.") — it
    # needs an ISO date string literal instead. Confirmed via scripts/probe_records.py.
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    date_field = config.RALEIGH_PERMIT_FIELDS["issue_date"]
    desc_field = config.RALEIGH_PERMIT_FIELDS["description"]
    value_field = config.RALEIGH_PERMIT_FIELDS["valuation"]

    keyword_clause = " OR ".join(
        f"UPPER({desc_field}) LIKE '%{kw.upper()}%'" for kw in config.RENOVATION_KEYWORDS
    )
    exclude_clause = " OR ".join(
        f"UPPER({desc_field}) LIKE '%{kw.upper()}%'" for kw in config.RENOVATION_EXCLUDE_KEYWORDS
    )
    where = (
        f"{date_field} >= '{cutoff_str}' AND {value_field} >= {config.RENOVATION_MIN_VALUE} "
        f"AND permitclassmapped = 'Residential' AND UPPER(workclass) NOT LIKE '%NEW%' "
        f"AND ({keyword_clause}) AND NOT ({exclude_clause})"
    )

    raw = _arcgis_query(config.RALEIGH_PERMITS_URL, where, n=200)
    return [_map_fields(r, config.RALEIGH_PERMIT_FIELDS) for r in raw]


def fetch_parcel_by_pin(pin: str) -> dict | None:
    """Look up the Wake County tax record for one parcel by its exact PIN —
    used only to enrich a candidate with year built / heated sqft / assessed
    value / deed date. Optional: a miss here doesn't disqualify a candidate."""
    if not pin:
        return None
    pin_field = config.WAKE_PARCEL_FIELDS["pin"]
    safe = str(pin).replace("'", "''")
    where = f"{pin_field} = '{safe}'"
    raw = _arcgis_query(config.WAKE_PARCELS_URL, where, n=1)
    if not raw:
        return None
    return _map_fields(raw[0], config.WAKE_PARCEL_FIELDS)


def find_renovation_candidates() -> list[dict]:
    """Recent renovation permits, each enriched with parcel tax-record facts
    where available.

    Returns a list of merged candidate dicts (permit fields + optional parcel
    enrichment), or a single-item list with an "_error" key if the permit
    fetch itself fails (network unreachable, endpoint down, schema mismatch)
    — same convention as leaddesk.sources.reddit, so callers handle both
    sources identically.
    """
    try:
        permits = fetch_recent_renovation_permits()
    except Exception as exc:
        return [{"_error": f"wake_records: could not fetch permits ({exc})"}]

    candidates = []
    for permit in permits:
        enrichment = {}
        try:
            parcel = fetch_parcel_by_pin(permit.get("pin"))
            if parcel:
                enrichment = parcel
        except Exception:
            pass  # enrichment is best-effort; the permit signal stands alone
        candidates.append({**permit, **enrichment})
    return candidates
