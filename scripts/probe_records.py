"""One-time discovery probe: confirmed schema check for the two services the
pipeline actually queries (see leaddesk/config.py).

Runs in GitHub Actions (which can reach the county/city servers) and prints
full field lists + sample rows so the records integration is built against
verified facts instead of guesses. Read-only; a handful of requests total.
"""

import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "leaddesk-probe/0.1 (public open-data discovery; one-time; low volume)"}

TARGETS = {
    "Raleigh permits (issued past 180 days)": (
        "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/"
        "Building_Permits_Issued_Past_180_Days/FeatureServer/0"
    ),
    "Wake parcels": "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/FeatureServer/0",
    "Wake parcels (alt domain)": "https://maps.wake.gov/arcgis/rest/services/Property/Parcels/MapServer/0",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def section(title):
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def probe(name, url):
    section(name)
    print("url:", url)
    try:
        meta = get(url + "?f=json")
        fields = [(f["name"], f.get("type", "")) for f in meta.get("fields", [])]
        print(f"ALL fields ({len(fields)}):")
        for fname, ftype in fields:
            print(f"  {fname}  ({ftype})")
    except Exception as e:
        print("METADATA FAILED:", e)
        return
    try:
        q = f"{url}/query?where=1%3D1&outFields=*&resultRecordCount=2&f=json"
        d = get(q)
        for feat in d.get("features", [])[:2]:
            print("sample:", json.dumps(feat.get("attributes", {}), default=str))
    except Exception as e:
        print("SAMPLE FAILED:", e)


def main():
    for name, url in TARGETS.items():
        probe(name, url)


if __name__ == "__main__":
    main()
