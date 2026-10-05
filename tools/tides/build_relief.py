#!/usr/bin/env python3
"""Cut a Mercator-projected shaded-relief image for each slice, for the story player's relief look.

Source: Natural Earth 1:50m Shaded Relief (SR_50M.tif, public domain), from
https://naturalearth.s3.amazonaws.com/50m_raster/SR_50M.zip . Flat ground is pushed to
white, so the image can be multiplied over the state colours without tinting them.

  python tools/tides/build_relief.py path/to/SR_50M.tif
"""
import json, math, pathlib, sys
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/tides/assets"
WIDTH = 1500


def mercator_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def cut(a, bbox):
    lon0, lat0, lon1, lat1 = bbox
    h, w = a.shape
    ppd = w / 360
    y0, y1 = mercator_y(lat1), mercator_y(lat0)
    outh = int(WIDTH * (y0 - y1) / math.radians(lon1 - lon0))
    lats = np.degrees(2 * np.arctan(np.exp(np.linspace(y0, y1, outh))) - math.pi / 2)
    rows = ((90 - lats) * ppd).astype(int).clip(0, h - 1)
    cols = ((np.linspace(lon0, lon1, WIDTH) + 180) * ppd).astype(int).clip(0, w - 1)
    out = a[np.ix_(rows, cols)].astype(float)
    out = np.clip(out / np.percentile(out, 50), 0, 1) ** 1.6 * 255
    return Image.fromarray(out.astype("uint8"))


def main(tif):
    Image.MAX_IMAGE_PIXELS = None
    a = np.asarray(Image.open(tif).convert("L"))
    OUT.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "tools/tides/curated").glob("*.json")):
        s = json.loads(f.read_text())
        if "clip" not in s:
            continue
        path = OUT / f"relief-{s['id']}.jpg"
        cut(a, s["clip"]).save(path, quality=80)
        print(path.name, path.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1])
