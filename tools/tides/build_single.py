#!/usr/bin/env python3
"""Bundle docs/tides into one self-contained HTML file (for previews/artifacts).

  python tools/tides/build_single.py OUT.html
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / "docs/tides"
D3_CDN = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"


def main(out):
    html = (ROOT / "index.html").read_text()
    manifest = json.loads((ROOT / "data/slices.json").read_text())["slices"]
    data = {m["id"]: json.loads((ROOT / m["file"]).read_text()) for m in manifest}
    inline = json.dumps({"manifest": manifest, "data": data}, ensure_ascii=False, separators=(",", ":"))
    html = html.replace('<link rel="stylesheet" href="tides.css">', "<style>\n" + (ROOT / "tides.css").read_text() + "</style>")
    html = html.replace('<script src="vendor/d3.min.js"></script>', f'<script src="{D3_CDN}"></script>')
    html = html.replace('<script src="time.js"></script>\n', "")
    html = html.replace('<script src="tides.js"></script>',
                        "<script>window.TIDES_INLINE=" + inline.replace("</", "<\\/") + ";</script>\n<script>\n"
                        + (ROOT / "time.js").read_text() + "\n" + (ROOT / "tides.js").read_text() + "</script>")
    # Artifact hosts wrap the page in their own document skeleton, so drop ours.
    for tag in ("<!DOCTYPE html>", '<html lang="en">', "<head>", "</head>", "<body>", "</body>", "</html>",
                '<meta charset="utf-8">'):
        html = html.replace(tag, "")
    pathlib.Path(out).write_text(html.strip() + "\n")
    print(f"{out}: {len(html.encode()) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
