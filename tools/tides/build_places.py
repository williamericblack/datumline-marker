#!/usr/bin/env python3
"""Who ruled this place? Builds docs/tides/data/places.json for the family-origins page.

For every Natural Earth 1:10m populated place (public domain), look up which polity's
polygon contains it in each historical-basemaps snapshot from 3000 BC on, and keep only
the years where the answer changes (run-length encoded).

  python tools/tides/build_places.py --basemaps <dir> --places ne_10m_populated_places_simple.geojson
"""
import argparse, json, pathlib
from shapely.geometry import shape, Point, MultiPolygon, mapping
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/tides/data/places.json"
BASEMAP_COMMIT = "da7a4b735ecef70aebdc9c73e409d8a2500d50f3"
FIRST_YEAR = -3000
# Labels in the basemap's 1920 and 1930 drafts that use names those places only took
# decades later. Keyed by (basemap year, label as built by ruler()).
CORRECTIONS = {
    **{(y, "Ghana"): "Gold Coast (United Kingdom)" for y in (1920, 1930)},
    **{(y, "Zambia"): "Northern Rhodesia (United Kingdom)" for y in (1920, 1930)},
    **{(y, "Zimbabwe"): "Southern Rhodesia (United Kingdom)" for y in (1920, 1930)},
    **{(y, "Zaire (Belgium)"): "Belgian Congo (Belgium)" for y in (1920, 1930)},
    (1930, "White Russia"): "USSR",
    (1945, "Zaire"): "Belgian Congo (Belgium)",
}


def rnd(o, nd):
    return [rnd(x, nd) for x in o] if isinstance(o, (list, tuple)) else round(o, nd)


def year_of(filename):
    stem = filename.removeprefix("world_").removesuffix(".geojson")
    return -int(stem[2:]) if stem.startswith("bc") else int(stem)


def ruler(props):
    name, subj = props.get("NAME"), props.get("SUBJECTO")
    if not name:
        return None
    if subj and subj not in (name, "None") and subj.lower() != name.lower() and f"({subj})" not in name:
        return f"{name} ({subj})"
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basemaps", required=True)
    ap.add_argument("--places", required=True)
    a = ap.parse_args()
    files = sorted((f.name for f in pathlib.Path(a.basemaps).glob("world_*.geojson")), key=year_of)
    files = [f for f in files if year_of(f) >= FIRST_YEAR]
    pts = json.loads(pathlib.Path(a.places).read_text())["features"]
    places = [[p["properties"]["name"], p["properties"].get("adm1name") or "", p["properties"]["adm0name"],
               round(p["properties"]["latitude"], 3), round(p["properties"]["longitude"], 3), p["properties"]["pop_max"]]
              for p in pts]
    places.sort(key=lambda p: -p[5])
    geoms = [Point(p[4], p[3]) for p in places]
    names, name_ix, runs = [], {}, [[] for _ in places]
    years = [year_of(f) for f in files]
    for yi, f in enumerate(files):
        polys, labels = [], []
        for feat in json.loads((pathlib.Path(a.basemaps) / f).read_text())["features"]:
            r = ruler(feat["properties"])
            r = CORRECTIONS.get((year_of(f), r), r)
            if r is None or not feat.get("geometry"):
                continue
            try:
                polys.append(shape(feat["geometry"]).buffer(0)); labels.append(r)
            except Exception:
                continue
        tree = STRtree(polys)
        for pi, g in enumerate(geoms):
            hit = None
            for k in tree.query(g, predicate="intersects"):
                hit = labels[k]; break
            ix = -1 if hit is None else name_ix.setdefault(hit, len(names))
            if ix == len(names):
                names.append(hit)
            if not runs[pi] or runs[pi][-1][1] != ix:
                runs[pi].append([yi, ix])
        print(f, len(polys))
    out = {"source": {"basemaps": f"aourednik/historical-basemaps@{BASEMAP_COMMIT[:7]} (GPL-3.0)",
                      "places": "Natural Earth 1:10m populated places (public domain)"},
           "years": years, "names": names,
           "places": [p[:5] for p in places], "runs": runs}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    # A light present-day outline for the page's locator map.
    world = json.loads((pathlib.Path(a.basemaps) / "world_2010.geojson").read_text())["features"]
    feats = []
    for feat in world:
        try:
            g = shape(feat["geometry"]).buffer(0).simplify(0.25, preserve_topology=True)
        except Exception:
            continue
        if g.is_empty:
            continue
        polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
        polys = [orient(p, sign=-1.0) for p in polys if p.area > 0.05]
        if polys:
            m = mapping(MultiPolygon(polys))
            feats.append({"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": rnd(m["coordinates"], 2)}})
    (OUT.parent / "world-outline.json").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    print(OUT, OUT.stat().st_size // 1024, "KB", len(places), "places", len(names), "names")


if __name__ == "__main__":
    main()
