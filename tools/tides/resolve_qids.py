#!/usr/bin/env python3
"""Resolve every source title in the curated slices to a Wikidata QID.

Each event, campaign and status rule cites an English Wikipedia title. This maps
those titles to QIDs via the Wikidata API and writes tools/tides/curated/qids.json
({title: QID or null}). Titles that do not resolve are printed so they can be fixed.
Needs network access to www.wikidata.org.

  python tools/tides/resolve_qids.py
"""
import json, pathlib, urllib.parse, urllib.request

CURATED = pathlib.Path(__file__).resolve().parent / "curated"
API = "https://www.wikidata.org/w/api.php"


def titles():
    out = set()
    for f in CURATED.glob("*.json"):
        if f.name == "qids.json":
            continue
        s = json.loads(f.read_text())
        out |= {e[7] for e in s["events"]} | {a[5] for a in s["arrows"]} | {r[4] for r in s["rules"]}
    return sorted(out)


def resolve(batch):
    q = urllib.parse.urlencode({"action": "wbgetentities", "sites": "enwiki", "titles": "|".join(batch),
                                "props": "sitelinks", "sitefilter": "enwiki", "redirects": "yes", "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "tides-qid-resolver/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        ents = json.loads(r.read())["entities"]
    found = {}
    for qid, e in ents.items():
        if qid.startswith("Q"):
            found[e["sitelinks"]["enwiki"]["title"]] = qid
    return found


def main():
    ts, found = titles(), {}
    for i in range(0, len(ts), 50):
        found.update(resolve(ts[i:i + 50]))
    result = {t: found.get(t) for t in ts}
    (CURATED / "qids.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    missing = [t for t, q in result.items() if not q]
    print(f"{len(ts) - len(missing)}/{len(ts)} titles resolved")
    for t in missing:
        print("UNRESOLVED:", t)


if __name__ == "__main__":
    main()
