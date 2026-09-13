#!/usr/bin/env python3
"""Daily marking run. Zero-spend, public sources only.

Writes the machine feed (docs/feed.json), the full evidence record
(docs/marks.json) and a methodology sidecar (docs/methodology.json).

docs/index.html is NOT written here. The published page is a checked-in
static shell that fetches feed.json in the visitor's browser and renders
the cohort from it, so the page and the feed cannot disagree and the page
can report its own staleness when this job stops running. Regenerating it
per run would overwrite that shell. methodology.json exists so the page
can show the live weight vector and grade bands without restating them.

GitHub Pages serves docs/ from branch main.
"""
import json, pathlib, datetime as dt, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from datumline_mcp.harvester import npm_package
from datumline_mcp.normalize import derive
from datumline_mcp.scorer import ScoreInput, score_record
from datumline_mcp.model import WEIGHT_VECTORS, LAYERS, GRADE_BANDS

OUT = pathlib.Path("docs"); OUT.mkdir(exist_ok=True)
now = dt.datetime.now(dt.timezone.utc).isoformat()
cohort = json.loads(pathlib.Path("cohort.json").read_text())

prev = {}
if (OUT / "marks.json").exists():
    prev = {m["entity_id"]: m for m in json.loads((OUT / "marks.json").read_text()).get("marks", [])}

marks, errors = [], []
for name in cohort:
    try:
        rec = npm_package(name)
    except Exception as e:
        errors.append({"entity_id": name, "error": str(e)}); continue
    d = derive(rec.payload)
    p = prev.get(name, {}).get("observations", {})
    if p.get("maintainers") is not None and p["maintainers"] != d["observations"]["maintainers"]:
        d["flags"]["maintainer_transfer_under_90d"] = True
    res = score_record(ScoreInput(
        entity_id=name, releases=d["releases"], registry_age_days=d["registry_age_days"],
        layer_scores=d["layer_scores"], flags=d["flags"],
        evidence=[{"source_url": rec.source_url, "artifact_hash": rec.artifact_hash,
                   "retrieved_at": rec.retrieved_at}]))
    res["observations"] = d["observations"]; res["as_of"] = now
    marks.append(res)

marks_doc = {"schema": "datumline.marks/v0.3-rc", "generated_at": now,
             "methodology": "v0.3-rc PROVISIONAL - layer derivation not locked",
             "cohort_size": len(cohort), "rated": sum(1 for m in marks if m["status"] == "RATED"),
             "errors": errors, "marks": marks}

SUPPRESS = {"DL-4", "DL-5"}
feed = [{"entity_id": m["entity_id"],
         "grade": m["vectors"]["W-C"]["grade"] if m["status"] == "RATED" else None,
         "status": m["status"], "as_of": now} for m in marks]
for f in feed:
    if f["grade"] in SUPPRESS:
        f["grade"], f["status"] = None, "IN MARKING"
feed_doc = {"schema": "datumline.feed/v0.3-rc", "last_marked": now, "entries": feed}


(OUT / "marks.json").write_text(json.dumps(marks_doc, indent=2))
(OUT / "feed.json").write_text(json.dumps(feed_doc, indent=2))
(OUT / "methodology.json").write_text(json.dumps({
    "schema": "datumline.methodology/v0.3-rc",
    "generated_at": now,
    "vector": "W-C",
    "label": WEIGHT_VECTORS["W-C"]["label"],
    "layers": list(LAYERS),
    "weights": WEIGHT_VECTORS["W-C"]["weights"],
    "grade_bands": [{"grade": b.grade, "maximum": b.maximum} for b in GRADE_BANDS],
}, indent=2))

print(f"marked {len(marks)}/{len(cohort)}  rated={marks_doc['rated']}"
      f"  errors={len(errors)}  last_marked={now}  wrote docs/feed.json docs/marks.json docs/methodology.json")
