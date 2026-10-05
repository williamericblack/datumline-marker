/* TIDES Daily: five historical maps, guess the year of each.
 * Everyone gets the same five on a given UTC day (seeded by the day number). Each round
 * shows the borders at a sourced event's date, with the event's place marked but not named.
 * Score: 100 for the exact year, falling to 0 at a quarter of the slice's span away.
 */
(function () {
  "use strict";
  const TT = window.TIDES_TIME, d = TT.parse, ROUNDS = 5;
  const EPOCH = Date.UTC(2026, 9, 5); // day 1 = 5 Oct 2026
  const DAY = 86400000, today = Math.floor((Date.now() - EPOCH) / DAY) + 1;
  const STORE = "tides-daily-" + today;

  function rng(seed) { // mulberry32
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  const yearOf = t => new Date(t).getUTCFullYear();             // astronomical year
  const tOfYear = y => { const D = new Date(Date.UTC(2000, 6, 1)); D.setUTCFullYear(y); return D.getTime(); };
  const wiki = t => "https://en.wikipedia.org/wiki/" + encodeURIComponent(t.replace(/ /g, "_"));
  const emoji = p => p >= 90 ? "🟩" : p >= 60 ? "🟨" : p >= 25 ? "🟧" : "⬛";

  const svg = d3.select("#stage"), view = d3.select("#view");
  let proj, path, rounds = [], idx = 0, results = [], slices = {};

  function load(k, fallback) { try { return JSON.parse(localStorage.getItem(k)) || fallback; } catch (e) { return fallback; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage blocked: game still works */ } }

  async function init() {
    const man = (await (await fetch("data/slices.json")).json()).slices;
    const all = await Promise.all(man.map(m => fetch(m.file).then(r => r.json())));
    all.forEach(s => {
      s.rulesC = s.rules.map(r => [new RegExp(r[0]), r[1], d(r[2]), d(r[3])]);
      s.bc = s.start[0] === "-";
      slices[s.id] = s;
    });
    const R = rng(today * 7919);
    const order = man.map(m => m.id).sort(() => R() - .5).slice(0, ROUNDS);
    rounds = order.map(id => {
      const s = slices[id], pool = s.events.filter(e => e[6] >= 3);
      const e = pool[Math.floor(R() * pool.length)];
      return { s, e: { n: e[0], ds: e[1], t: d(e[1]), lat: e[2], lon: e[3], sides: e[4], res: e[5], src: e[7] } };
    });
    d3.select("#dayno").text("#" + today);
    results = load(STORE, []);
    idx = results.length;
    drawDots();
    if (idx >= ROUNDS) return finish();
    showRound();
    let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => drawMap(rounds[Math.min(idx, ROUNDS - 1)]), 150); });
  }

  function color(s, b) { const v = s.blocs[b] || s.blocs[s.default_bloc]; return v[2] === "hatch" ? `url(#gh-${s.id}-${b})` : v[1]; }
  function bloc(s, n, t) { for (const r of s.rulesC) if (r[0].test(n) && t >= r[2] && t < r[3]) return r[1]; return s.default_bloc; }
  function drawMap(r) {
    const s = r.s, t = r.e.t, el = document.getElementById("map");
    const W = el.clientWidth, H = el.clientHeight, v = s.views[0];
    proj = d3.geoMercator().fitExtent([[10, 10], [W - 10, H - 10]],
      { type: "MultiPoint", coordinates: [v[2], v[3], [v[2][0], v[3][1]], [v[3][0], v[2][1]]] });
    path = d3.geoPath(proj);
    let y = s.snapshots[0].year; for (const x of s.snapshots) if (t >= d(x.from)) y = x.year;
    const feats = s.borders[String(y)];
    const defs = d3.select("#defs"); defs.selectAll("*").remove();
    for (const [k, v2] of Object.entries(s.blocs)) if (v2[2] === "hatch") {
      const p = defs.append("pattern").attr("id", `gh-${s.id}-${k}`).attr("patternUnits", "userSpaceOnUse").attr("width", 6).attr("height", 6).attr("patternTransform", "rotate(45)");
      p.append("rect").attr("width", 6).attr("height", 6).attr("fill", v2[1]);
      p.append("rect").attr("width", 2.6).attr("height", 6).attr("fill", "#14171f");
    }
    d3.select("#states").selectAll("*").remove();
    d3.select("#states").selectAll("path").data(feats).enter().append("path").attr("class", "state")
      .attr("d", path).style("fill", f => color(s, bloc(s, f.properties.n, t)));
    const big = feats.filter(f => f.properties.a > (s.label_min ?? 4) && !/culture|hunter-gatherers|nomads|tribes|minor states/i.test(f.properties.n)).sort((a, b) => b.properties.a - a.properties.a).slice(0, W < 640 ? 6 : 12);
    d3.select("#labels").selectAll("*").remove();
    d3.select("#labels").selectAll("text").data(big).enter().append("text").attr("class", "lbl").attr("font-size", 10)
      .attr("transform", f => `translate(${path.centroid(f)})`).text(f => f.properties.n);
    const [x, yy] = proj([r.e.lon, r.e.lat]);
    const g = d3.select("#target"); g.selectAll("*").remove();
    g.append("circle").attr("class", "tring").attr("cx", x).attr("cy", yy).attr("r", 14);
    g.append("circle").attr("class", "tgt").attr("cx", x).attr("cy", yy).attr("r", 5);
  }

  function showRound() {
    const r = rounds[idx], s = r.s;
    d3.select("#reveal").attr("hidden", true); d3.select("#done").attr("hidden", true); d3.select("#guessbox").attr("hidden", null);
    d3.select("#round").text(`Map ${idx + 1} of ${ROUNDS} · ${s.title}`);
    d3.select("#clue").text(`Something happened at the marked spot: ${r.e.sides || "an event"}. What year is it?`);
    const y0 = yearOf(d(s.start)), y1 = yearOf(d(s.end));
    const sl = d3.select("#slider").attr("min", y0).attr("max", y1).attr("step", 1).property("value", Math.round((y0 + y1) / 2));
    d3.select("#rmin").text(TT.year(tOfYear(y0), s.bc)); d3.select("#rmax").text(TT.year(tOfYear(y1), s.bc));
    const show = () => d3.select("#guessyear").text(TT.year(tOfYear(+sl.property("value")), s.bc));
    sl.on("input", show); show();
    drawMap(r);
  }

  function submit() {
    const r = rounds[idx], s = r.s, guess = +d3.select("#slider").property("value");
    const actual = yearOf(r.e.t), span = yearOf(d(s.end)) - yearOf(d(s.start));
    const diff = Math.abs(guess - actual);
    const pts = Math.round(100 * Math.max(0, 1 - diff / Math.max(1, span * .25)));
    results.push(pts); save(STORE, results); drawDots();
    d3.select("#guessbox").attr("hidden", true); d3.select("#reveal").attr("hidden", null);
    d3.select("#r-score").text(`${emoji(pts)} ${pts} points · ${diff === 0 ? "exact year" : diff + (diff === 1 ? " year" : " years") + " off"}`);
    d3.select("#r-event").text(`${r.e.n} — ${TT.label(r.e.ds, s.bc)}`);
    d3.select("#r-detail").html("");
    d3.select("#r-detail").append("span").text(r.e.res + " ");
    d3.select("#r-detail").append("a").attr("href", wiki(r.e.src)).attr("target", "_blank").attr("rel", "noopener").text("Source ↗");
    d3.select("#next").text(idx + 1 < ROUNDS ? "Next map" : "See my result");
  }
  function next() { idx++; if (idx >= ROUNDS) finish(); else showRound(); }

  function shareText() {
    const total = results.reduce((a, b) => a + b, 0);
    return `TIDES Daily #${today} ${results.map(emoji).join("")} ${total}/${ROUNDS * 100}\n${location.origin}${location.pathname}`;
  }
  function finish() {
    d3.select("#guessbox").attr("hidden", true); d3.select("#reveal").attr("hidden", true); d3.select("#done").attr("hidden", null);
    const total = results.reduce((a, b) => a + b, 0);
    d3.select("#round").text("Today's result");
    d3.select("#clue").text("Come back tomorrow for five new maps.");
    d3.select("#d-score").text(`${total} of ${ROUNDS * 100}`);
    d3.select("#share").text(shareText());
    drawMap(rounds[ROUNDS - 1]);
  }
  function drawDots() {
    d3.select("#dots").text(Array.from({ length: ROUNDS }, (_, i) => i < results.length ? emoji(results[i]) : "·").join(" "));
  }

  d3.select("#submit").on("click", submit);
  d3.select("#next").on("click", next);
  d3.select("#copy").on("click", function () {
    const btn = d3.select(this), txt = shareText();
    const fallback = () => { const r = document.createRange(); r.selectNodeContents(document.getElementById("share")); getSelection().removeAllRanges(); getSelection().addRange(r); btn.text("Selected — copy it"); };
    if (navigator.clipboard) navigator.clipboard.writeText(txt).then(() => btn.text("Copied"), fallback); else fallback();
  });
  init();
})();
