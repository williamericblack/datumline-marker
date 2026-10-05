#!/usr/bin/env python3
"""Build TIDES slice data: basemap snapshots + curated tables -> docs/tides/data/<slice>.json.

Borders come from aourednik/historical-basemaps (GPL-3.0), pinned to one commit so
every snapshot is citable. Each slice is clipped to its bbox and simplified; the
curated file (tools/tides/curated/<slice>.json) supplies events, campaigns, status
rules and eras, each row carrying its source title.

  python tools/tides/build_slices.py --basemaps <dir with world_<year>.geojson>
  (without --basemaps the pinned files are downloaded from raw.githubusercontent.com)
"""
import argparse, json, pathlib, urllib.request
from shapely.geometry import shape, box, mapping, Polygon, MultiPolygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

BASEMAP_REPO = "aourednik/historical-basemaps"
BASEMAP_COMMIT = "da7a4b735ecef70aebdc9c73e409d8a2500d50f3"
ROOT = pathlib.Path(__file__).resolve().parents[2]
CURATED = ROOT / "tools/tides/curated"
OUT = ROOT / "docs/tides/data"
SLICES = ["europe", "americas", "west-africa", "rome", "mongols", "inca"]


def basemap_file(year):
    """Basemap files name BC years "bc<n>"; a slice writes 200 BC as year -200."""
    return f"world_bc{-year}.geojson" if year < 0 else f"world_{year}.geojson"


def basemap_url(year):
    return f"https://raw.githubusercontent.com/{BASEMAP_REPO}/{BASEMAP_COMMIT}/geojson/{basemap_file(year)}"


def date_key(s):
    """Sort key for TIDES dates, including BC dates written with a leading minus."""
    neg, parts = s.startswith("-"), s.lstrip("-").split("-")
    y = int(parts[0])
    return (-y if neg else y, int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1)


def load_basemap(year, local):
    if local:
        return json.loads((pathlib.Path(local) / basemap_file(year)).read_text())
    with urllib.request.urlopen(basemap_url(year), timeout=60) as r:
        return json.loads(r.read())


def rnd(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        return [rnd(o, nd) for o in obj]
    return round(obj, nd)


def clip(fc, bbox, tol, meter_box=None):
    clipbox = box(*bbox)
    by_name = {}
    for f in fc["features"]:
        name = f["properties"].get("NAME")
        if not name or not f.get("geometry"):
            continue
        try:
            g = shape(f["geometry"]).buffer(0)
        except Exception:
            continue
        if not g.intersects(clipbox):
            continue
        g = g.intersection(clipbox)
        if g.is_empty or g.area < 0.02:
            continue
        by_name.setdefault(name, []).append(g)
    feats = []
    for name, gs in sorted(by_name.items()):
        g = unary_union(gs).simplify(tol, preserve_topology=True)
        if g.is_empty:
            continue
        if g.geom_type == "GeometryCollection":
            g = unary_union([p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
            if g.is_empty:
                continue
        # d3-geo reads ring winding spherically: exterior rings must be clockwise, or the
        # polygon is drawn as the whole globe minus the state.
        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
        g = MultiPolygon([orient(p, sign=-1.0) for p in polys]) if len(polys) > 1 else orient(polys[0], sign=-1.0)
        m = mapping(g)
        props = {"n": name, "a": round(g.area, 2)}
        if meter_box:  # land area inside the meter's region, for "share of Europe" style counters
            props["m"] = round(g.intersection(box(*meter_box)).area, 3)
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": m["type"], "coordinates": rnd(m["coordinates"])}})
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basemaps", help="directory holding world_<year>.geojson (pinned commit)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cache, manifest = {}, []
    for sid in SLICES:
        s = json.loads((CURATED / f"{sid}.json").read_text())
        s["borders"] = {}
        for snap in s["snapshots"]:
            y = snap["year"]
            if y not in cache:
                cache[y] = load_basemap(y, args.basemaps)
            s["borders"][str(y)] = clip(cache[y], s["clip"], s["simplify"], s.get("meter_box"))
            snap["source"] = {"file": f"geojson/{basemap_file(y)}", "repo": BASEMAP_REPO,
                              "commit": BASEMAP_COMMIT, "license": "GPL-3.0",
                              "url": f"https://github.com/{BASEMAP_REPO}/blob/{BASEMAP_COMMIT}/geojson/{basemap_file(y)}"}
        s["events"].sort(key=lambda e: date_key(e[1]))
        path = OUT / f"{sid}.json"
        path.write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")))
        manifest.append({"id": sid, "title": s["title"], "period": s["period"], "tagline": s["tagline"],
                         "file": f"data/{sid}.json", "events": len(s["events"]), "arrows": len(s["arrows"]),
                         "snapshots": [x["year"] for x in s["snapshots"]]})
        print(f"{sid}: {path.stat().st_size // 1024} KB, {len(s['events'])} events, "
              f"{sum(len(v) for v in s['borders'].values())} polygons")
    (OUT / "slices.json").write_text(json.dumps({"slices": manifest}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
