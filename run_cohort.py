#!/usr/bin/env python3
"""Daily marking run. Zero-spend, public sources only.

Writes the machine feed (JSON) AND a deterministic static page
(docs/index.html) from the SAME run data, so the published page and the
feed can never disagree. GitHub Pages serves docs/ from branch main.
"""
import json, pathlib, datetime as dt, sys, html as _html
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


def render_index_html(marks_doc: dict, feed_doc: dict) -> str:
    """Deterministic render of the public page from run data ONLY.

    No wall-clock reads occur here: every value is taken from the passed-in
    data. Rows are sorted by entity_id and dates are shown to the day, so
    rendering the same run data always yields a byte-identical page.
    """
    esc = _html.escape
    wc = WEIGHT_VECTORS["W-C"]
    wsum = sum(wc["weights"].values())
    as_of_by_id = {m["entity_id"]: (m.get("as_of") or "") for m in marks_doc["marks"]}
    entries = sorted(feed_doc["entries"], key=lambda e: e["entity_id"])

    rows = []
    for e in entries:
        name = esc(e["entity_id"])
        grade = e["grade"] if e["grade"] else e["status"]
        date_marked = esc((as_of_by_id.get(e["entity_id"], "") or "")[:10])
        rows.append(
            f'      <tr><td class="name">{name}</td>'
            f'<td class="grade">{esc(str(grade))}</td>'
            f'<td class="date">{date_marked}</td></tr>')
    rows_html = "\n".join(rows)

    wrows = "\n".join(
        f'      <tr><td class="layer">{esc(l)}</td>'
        f'<td class="w">{wc["weights"][l]}</td><td class="w">{wsum}</td></tr>'
        for l in LAYERS)

    bands = ", ".join(f"{b.grade} ≤ {b.maximum}" for b in GRADE_BANDS)
    last_marked = esc((feed_doc.get("last_marked") or "")[:10])
    rated_n = marks_doc["rated"]; cohort_n = marks_doc["cohort_size"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Datumline Marker — MCP package marks (v0.3-rc, provisional)</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width: 880px; margin: 2rem auto; padding: 0 1rem; color: #111; line-height: 1.55; }}
  h1 {{ font-size: 1.55rem; margin-bottom: .15rem; }}
  h2 {{ font-size: 1.05rem; margin: .2rem 0 .4rem; }}
  p.sub {{ color: #555; margin-top: 0; }}
  section {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.1rem 0; }}
  section.facts {{ border-left: 6px solid #1a7f37; background: #fbfffb; }}
  section.conclusions {{ border-left: 6px solid #9a6700; background: #fffdf6; }}
  .tag {{ display: inline-block; font-size: .70rem; letter-spacing: .05em; text-transform: uppercase;
         font-weight: 700; padding: .12rem .5rem; border-radius: 4px; margin-bottom: .5rem; }}
  .facts .tag {{ background: #1a7f37; color: #fff; }}
  .conclusions .tag {{ background: #9a6700; color: #fff; }}
  hr.boundary {{ border: 0; border-top: 2px dashed #bbb; margin: 1.4rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .6rem; }}
  th, td {{ text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #eaeaea; }}
  th {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .03em; color: #555; }}
  td.name {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .92rem; }}
  td.grade {{ font-weight: 700; }}
  td.w {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.weights td.layer {{ text-transform: capitalize; }}
  footer {{ color: #777; font-size: .84rem; margin-top: 2rem; border-top: 1px solid #eee; padding-top: .8rem; }}
</style>
</head>
<body>
<h1>Datumline Marker</h1>
<p class="sub">Provisional security marks for a fixed cohort of MCP packages.
Methodology <strong>v0.3-rc — PROVISIONAL</strong>. Marks as of {last_marked}.
{rated_n} of {cohort_n} entities rated.</p>

<section class="facts">
  <span class="tag">Facts — observed &amp; marked</span>
  <h2>Rated table</h2>
  <p>Each row is one entity from the fixed cohort, named nominatively (reference only).
  Grade is the published W-C grade, or the entity's current marking status.
  “Date marked” is the date the underlying npm registry evidence was retrieved.</p>
  <table>
    <thead><tr><th>Name</th><th>Grade</th><th>Date marked</th></tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
  <p><a href="./feed.json">feed.json</a> — the machine-readable version of this table.</p>
</section>

<hr class="boundary">

<section class="conclusions">
  <span class="tag">Conclusions — methodology &amp; interpretation</span>
  <h2>How the grade is derived</h2>
  <p>Zero-spend, public sources only (the npm registry). Each package's public metadata is
  derived into five layer scores on a 1.0 (best) to 5.0 (worst) scale, combined by a weight
  vector, then banded into a grade. Grade bands: {bands}. This layer derivation is a
  <strong>candidate and is NOT locked</strong> (v0.3-rc).</p>

  <h2>W-C weight vector (“clean-sheet locked v0.3”)</h2>
  <p>The vector used for the grades in the table above:</p>
  <table class="weights">
    <thead><tr><th>Layer</th><th>Weight</th><th>Of</th></tr></thead>
    <tbody>
{wrows}
    </tbody>
  </table>

  <h2>What was NOT evaluated</h2>
  <ul>
    <li>No runtime, dynamic, or behavioral analysis — only static public registry metadata.</li>
    <li>No third-party security feeds, scanners, or paid data; no named public grading services consulted.</li>
    <li>Grades DL-4 and DL-5 are <strong>suppressed</strong> from the public feed and shown as
        “IN MARKING” pending review — a worst-grade result is not published here.</li>
    <li>Entities with fewer than 3 published releases or fewer than 90 days of registry history
        are <strong>Not Rated (NR)</strong>, not graded.</li>
    <li>The layer-derivation mapping itself is provisional and subject to change before v0.3 is locked.</li>
  </ul>
</section>

<footer>
  Nominative reference only; no endorsement, affiliation, sponsorship, or third-party marks are implied.
  Generated deterministically from the same run data as <a href="./feed.json">feed.json</a>.
</footer>
</body>
</html>
"""


(OUT / "marks.json").write_text(json.dumps(marks_doc, indent=2))
(OUT / "feed.json").write_text(json.dumps(feed_doc, indent=2))
(OUT / "index.html").write_text(render_index_html(marks_doc, feed_doc))

print(f"marked {len(marks)}/{len(cohort)}  rated={marks_doc['rated']}"
      f"  errors={len(errors)}  last_marked={now}  wrote docs/index.html docs/feed.json docs/marks.json")
