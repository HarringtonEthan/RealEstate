"""One-time discovery probe: what do Wake County / Raleigh public data servers expose?

Runs in GitHub Actions (which can reach the county servers) and prints service
directories, layer names, and field lists so the records integration can be
built against verified facts instead of guesses. Read-only; a handful of
requests total.
"""

import json
import urllib.request

UA = {"User-Agent": "leaddesk-probe/0.1 (public open-data discovery; one-time; low volume)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def section(title):
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def probe_arcgis_root(base):
    try:
        d = get(base + "?f=json")
        print("folders:", d.get("folders"))
        print("services:", [f"{s['name']} ({s['type']})" for s in d.get("services", [])])
        return d
    except Exception as e:
        print("FAILED:", e)
        return None


def probe_service_layers(url):
    try:
        d = get(url + "?f=json")
        for lyr in d.get("layers", []):
            print(f"  layer {lyr['id']}: {lyr['name']}")
        return d
    except Exception as e:
        print("  FAILED:", e)
        return None


def probe_layer_fields(url, keep=40):
    try:
        d = get(url + "?f=json")
        fields = [f["name"] for f in d.get("fields", [])]
        print(f"  fields ({len(fields)}):", fields[:keep])
        return fields
    except Exception as e:
        print("  FAILED:", e)
        return None


def sample_rows(url, where="1=1", n=2, out_fields="*"):
    try:
        q = (f"{url}/query?where={urllib.parse.quote(where)}&outFields={out_fields}"
             f"&resultRecordCount={n}&f=json")
        d = get(q)
        for feat in d.get("features", [])[:n]:
            attrs = feat.get("attributes", {})
            print("  sample:", json.dumps({k: attrs[k] for k in list(attrs)[:25]}, default=str)[:900])
    except Exception as e:
        print("  sample FAILED:", e)


import urllib.parse  # noqa: E402


def main():
    section("Wake County ArcGIS root (maps.wakegov.com)")
    root = probe_arcgis_root("https://maps.wakegov.com/arcgis/rest/services")
    if root:
        for folder in (root.get("folders") or [])[:20]:
            section(f"Wake folder: {folder}")
            probe_arcgis_root(f"https://maps.wakegov.com/arcgis/rest/services/{folder}")

    section("City of Raleigh ArcGIS org (services.arcgis.com/v400IkDOw1ad7Yad)")
    ral = probe_arcgis_root("https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services")
    if ral:
        permitish = [s for s in ral.get("services", [])
                     if any(k in s["name"].lower() for k in ("permit", "development"))]
        print("\npermit-ish services:", [s["name"] for s in permitish])
        for s in permitish[:4]:
            url = f"https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/{s['name']}/{s['type']}"
            section(f"Raleigh service: {s['name']}")
            meta = probe_service_layers(url)
            if meta and meta.get("layers"):
                lyr_url = f"{url}/{meta['layers'][0]['id']}"
                probe_layer_fields(lyr_url)
                sample_rows(lyr_url)

    section("Wake County open-data hub org candidates")
    # data.wake.gov is an ArcGIS Hub; its backing org serves FeatureServers on services*.arcgis.com.
    # The hub search API reveals the org and dataset service URLs.
    try:
        d = get("https://data.wake.gov/api/feed/dcat-us/1.1.json")
        items = d.get("dataset", [])
        print(f"DCAT feed OK — {len(items)} datasets. Matching parcels/permits/deeds:")
        for it in items:
            title = it.get("title", "")
            if any(k in title.lower() for k in ("parcel", "permit", "deed", "real estate", "property")):
                dist = it.get("distribution", [])
                urls = [x.get("accessURL") or x.get("downloadURL") for x in dist]
                print(" -", title, "|", [u for u in urls if u][:3])
    except Exception as e:
        print("DCAT feed FAILED:", e)


if __name__ == "__main__":
    main()
