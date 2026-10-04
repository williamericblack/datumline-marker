# TIDES

TIDES is an engine for animated historical maps at the scale of sovereign states. You press play and watch borders, battles and campaigns change. It ships with three slices:

| Slice | Period | Border snapshots |
|---|---|---|
| Europe | 1792–1815 | 1783, 1800, 1815 |
| Americas | 1775–1826 | 1783, 1800, 1815 |
| West Africa | 1878–1914 | 1880, 1900, 1914 |

The site lives in `docs/tides/`. GitHub Pages serves `docs/` from `main`, so the published page is at `/tides/` on the repo's Pages URL.

## How it works

- **The engine** (`docs/tides/tides.js`) knows nothing about any one region. A slice is a data file with:
  - border snapshots
  - dated status rules that tint each state (for example, Spanish crown → war of independence → independent state)
  - events, campaign arrows and era labels
- **Borders** come from [aourednik/historical-basemaps](https://github.com/aourednik/historical-basemaps), GPL-3.0, pinned at commit `da7a4b7`. Between snapshots, the rules tint each state; they do not redraw its polygon.
- **Sources:** every event, campaign and rule cites an English Wikipedia title. The in-page *Sources* panel lists all of them, and tapping an event or state shows its source.

## Build

```sh
python tools/tides/build_slices.py            # downloads the pinned basemaps; or pass --basemaps DIR
python tools/tides/build_single.py out.html   # one self-contained file for previews
python tools/tides/resolve_qids.py            # titles -> Wikidata QIDs (needs wikidata.org access)
```

To add a region, write `tools/tides/curated/<id>.json` with the same shape as the existing slices, add the id to `SLICES` in `build_slices.py`, and rebuild.

## Known gaps

- QIDs are not resolved yet. The build container's network policy blocks wikidata.org, so citations are Wikipedia titles until `resolve_qids.py` runs from a lane that can reach it.
- Only 3 border snapshots per slice. For example, the 1806–1813 French Empire is shown by tinting, not by its own polygons.
- The basemap's own errors carry through. Saint-Domingue/Haiti has no separate polygon before the 1815 snapshot, and the 1900 West Africa snapshot reflects the mid-1890s.
- Event coordinates are approximate, placed at the battle site or city.
