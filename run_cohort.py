#!/usr/bin/env python3
"""Daily marking run. Zero-spend, public sources only."""
import json, pathlib, datetime as dt, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from datumline_mcp.harvester import npm_package
from datumline_mcp.normalize import derive
from datumline_mcp.scorer import ScoreInput, score_record

OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
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

(OUT / "marks.json").write_text(json.dumps(
    {"schema": "datumline.marks/v0.3-rc", "generated_at": now,
     "methodology": "v0.3-rc PROVISIONAL - layer derivation not locked",
     "cohort_size": len(cohort), "rated": sum(1 for m in marks if m["status"] == "RATED"),
     "errors": errors, "marks": marks}, indent=2))

SUPPRESS = {"DL-4", "DL-5"}
feed = [{"entity_id": m["entity_id"],
         "grade": m["vectors"]["W-C"]["grade"] if m["status"] == "RATED" else None,
         "status": m["status"], "as_of": now} for m in marks]
for f in feed:
    if f["grade"] in SUPPRESS:
        f["grade"], f["status"] = None, "IN MARKING"
(OUT / "feed.json").write_text(json.dumps(
    {"schema": "datumline.feed/v0.3-rc", "last_marked": now, "entries": feed}, indent=2))

print(f"marked {len(marks)}/{len(cohort)}  rated={sum(1 for m in marks if m['status']=='RATED')}"
      f"  errors={len(errors)}  last_marked={now}")
