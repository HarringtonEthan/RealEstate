"""Debug probe: isolate which WHERE-clause fragment ArcGIS rejects.

Runs in GitHub Actions (which can reach the county/city servers). Tries the
permit query's clauses one at a time so a genuine syntax problem is pinpointed
instead of guessed at.
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "leaddesk-probe/0.1 (public open-data discovery; one-time; low volume)"}
URL = (
    "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/"
    "Building_Permits_Issued_Past_180_Days/FeatureServer/0"
)


def query(where, n=2):
    params = {"where": where, "outFields": "OBJECTID,issueddate,estprojectcost,description",
              "resultRecordCount": n, "f": "json"}
    url = f"{URL}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
        if "error" in data:
            print(f"  FAIL: {data['error']}")
        else:
            print(f"  OK: {len(data.get('features', []))} feature(s)")
    except Exception as e:
        print(f"  EXCEPTION: {e}")


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")

    tests = [
        ("baseline 1=1", "1=1"),
        ("date >= epoch ms", f"issueddate >= {cutoff_ms}"),
        ("date >= iso literal", f"issueddate >= '{cutoff_iso}'"),
        ("date >= TIMESTAMP literal", f"issueddate >= TIMESTAMP '{cutoff_iso} 00:00:00'"),
        ("value only", "estprojectcost >= 10000"),
        ("single LIKE", "UPPER(description) LIKE '%KITCHEN%'"),
        ("LIKE with OR (2)", "UPPER(description) LIKE '%KITCHEN%' OR UPPER(description) LIKE '%BATH%'"),
        ("date epoch + value", f"issueddate >= {cutoff_ms} AND estprojectcost >= 10000"),
        ("date epoch + value + LIKE",
         f"issueddate >= {cutoff_ms} AND estprojectcost >= 10000 AND (UPPER(description) LIKE '%KITCHEN%')"),
        ("date iso + value + LIKE",
         f"issueddate >= '{cutoff_iso}' AND estprojectcost >= 10000 AND (UPPER(description) LIKE '%KITCHEN%')"),
    ]
    for name, where in tests:
        print(f"\n{name}\n  where: {where}")
        query(where)


if __name__ == "__main__":
    main()
