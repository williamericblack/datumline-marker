/* TIDES Origins: who ruled this place, snapshot by snapshot, and at each family birth year. */
(function () {
  "use strict";
  const yl = y => y < 0 ? `${-y} BC` : String(y); // basemap years are historical (no year 0)
  const fold = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const BIRTHS = [["b-you", "You"], ["b-par", "Your parent"], ["b-gp", "Your grandparent"], ["b-ggp", "Your great-grandparent"]];
  let P, keys, world, slices = [], current = null;

  Promise.all([fetch("data/places.json").then(r => r.json()), fetch("data/world-outline.json").then(r => r.json()),
    fetch("data/slices.json").then(r => r.json())]).then(async ([p, w, man]) => {
    P = p; world = w; keys = P.places.map(x => fold(x[0]));
    slices = await Promise.all(man.slices.map(m => fetch(m.file).then(r => r.json()).then(s => ({ id: s.id, title: s.title, period: s.period, clip: s.clip }))));
    d3.select("#src").text(`Borders: ${P.source.basemaps}, a community-drafted historical atlas. Snapshots are years apart and some contain errors, so treat each line as approximate. Places: ${P.source.places}.`);
    const q = new URLSearchParams(location.search).get("place");
    if (q) { d3.select("#q").property("value", q); search(q, true); }
  });

  function search(text, pickFirst) {
    const t = fold(text.trim());
    const ul = d3.select("#matches"); ul.selectAll("*").remove();
    if (t.length < 2 || !P) return;
    const hits = [];
    for (let i = 0; i < keys.length && hits.length < 8; i++) if (keys[i].startsWith(t)) hits.push(i);
    for (let i = 0; i < keys.length && hits.length < 8; i++) if (!keys[i].startsWith(t) && keys[i].includes(t)) hits.push(i);
    if (pickFirst && hits.length) return pick(hits[0]);
    ul.selectAll("li").data(hits).enter().append("li").append("button").attr("role", "option")
      .html(i => { const x = P.places[i]; return `${esc(x[0])} <small>${esc([x[1], x[2]].filter(Boolean).join(", "))}</small>`; })
      .on("click", (e, i) => pick(i));
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function rulerAt(i, year) { // the snapshot in force in that year: the latest one not after it
    let name = null, snapYear = null;
    for (const [yi, ni] of P.runs[i]) { if (P.years[yi] > year) break; name = ni < 0 ? null : P.names[ni]; snapYear = P.years[yi]; }
    let last = null; for (const y of P.years) if (y <= year) last = y;
    return { name, snap: last ?? snapYear };
  }

  function pick(i) {
    current = i;
    const x = P.places[i];
    d3.select("#matches").selectAll("*").remove();
    d3.select("#q").property("value", x[0]);
    d3.select("#result").attr("hidden", null);
    d3.select("#place").text([x[0], x[1], x[2]].filter((v, k, a) => v && a.indexOf(v) === k).join(", "));
    drawLocator(x[3], x[4]);
    drawNotes();
    const inside = slices.filter(s => x[4] >= s.clip[0] && x[4] <= s.clip[2] && x[3] >= s.clip[1] && x[3] <= s.clip[3]);
    d3.select("#stories").html(inside.map(s => `<a href="index.html#${s.id}">Watch ${esc(s.title)} · ${esc(s.period)}</a>`).join(""));
    const tl = d3.select("#timeline"); tl.selectAll("*").remove();
    const runs = P.runs[i].slice().reverse();
    runs.forEach(([yi, ni], k) => {
      const from = P.years[yi], to = k ? P.years[runs[k - 1][0]] : null;
      const li = tl.append("li");
      li.append("span").attr("class", "yr").text(to ? `${yl(from)} – ${yl(to)}` : `${yl(from)} – today`);
      li.append("span").attr("class", "who").text(ni < 0 ? "Not mapped as part of any state" : P.names[ni]);
    });
    try { history.replaceState(null, "", "?place=" + encodeURIComponent(x[0])); } catch (e) { /* sandboxed */ }
  }

  function drawNotes() {
    const box = d3.select("#notes"); box.selectAll("*").remove();
    if (current == null) return;
    BIRTHS.forEach(([id, who]) => {
      const y = parseInt(d3.select("#" + id).property("value"), 10);
      if (!(y > -3000 && y <= new Date().getFullYear())) return;
      const r = rulerAt(current, y);
      const n = box.append("div").attr("class", "note");
      n.append("b").text(`${who}, born ${y}`);
      n.append("div").text(r.name ? `This place was part of ${r.name}.` : "This place was not mapped as part of any state.");
      n.append("div").attr("class", "m").text(`From the ${yl(r.snap)} map, the nearest one before that year.`);
    });
  }

  function drawLocator(lat, lon) {
    const svg = d3.select("#locator"); svg.selectAll("*").remove();
    const proj = d3.geoNaturalEarth1().fitSize([800, 400], { type: "Sphere" }), path = d3.geoPath(proj);
    svg.append("g").selectAll("path").data(world.features).enter().append("path").attr("d", path);
    const [x, y] = proj([lon, lat]);
    svg.append("circle").attr("class", "halo").attr("cx", x).attr("cy", y).attr("r", 10);
    svg.append("circle").attr("class", "dot").attr("cx", x).attr("cy", y).attr("r", 4);
  }

  d3.select("#q").on("input", function () { search(this.value, false); });
  d3.select("#q").on("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); search(this.value, true); } });
  BIRTHS.forEach(([id]) => d3.select("#" + id).on("input", drawNotes));
})();
