/* TIDES story player: a ~30 s scripted run through one slice, for clips and look tests.
 * Hash selects the variant: #<look>-<voice>[-rec], look = dark|paper|relief, voice = deadpan|epic.
 * "-rec" hides controls and starts at once, for screen recording.
 */
(function () {
  "use strict";
  const DAY = 86400000, HOOK_MS = 2400, DWELL_MS = 1500, TRAVEL_DAYS_PER_S = 300, END_HOLD_MS = 600;
  const d = s => Date.UTC(+s.slice(0, 4), s.length > 5 ? +s.slice(5, 7) - 1 : 0, s.length > 8 ? +s.slice(8, 10) : 1);
  const opts = location.hash.slice(1).split("-");
  const LOOK = ["dark", "paper", "relief"].find(x => opts.includes(x)) || "dark";
  const VOICE = opts.includes("epic") ? "epic" : "deadpan";
  const REC = opts.includes("rec");
  document.body.dataset.look = LOOK;
  if (REC) document.body.classList.add("rec");
  const INLINE = window.TIDES_STORY_INLINE || null;

  const svg = d3.select("#stage"), view = d3.select("#view");
  const proj = d3.geoMercator(), path = d3.geoPath(proj);
  let SL, ST, T, T0, T1, snap = null, beats, phase = "idle", dwellUntil = 0, last = 0, nextBeat = 0;

  async function load() {
    if (INLINE) return [INLINE.slice, INLINE.story];
    const [a, b] = await Promise.all([fetch("data/europe.json"), fetch("data/story-napoleon.json")]);
    return [await a.json(), await b.json()];
  }

  function bloc(name, t) {
    for (const r of SL.rulesC) if (r[0].test(name) && t >= r[2] && t < r[3]) return r[1];
    return "neu";
  }
  function snapshot(t) { let y = SL.snapshots[0].year; for (const x of SL.snapshots) if (t >= d(x.from)) y = x.year; return y; }

  function layout() {
    const top = 150, bottom = innerHeight - 190;
    const [a, b] = ST.view;
    proj.fitExtent([[12, top], [innerWidth - 12, Math.max(top + 100, bottom)]],
      { type: "MultiPoint", coordinates: [a, b, [a[0], b[1]], [b[0], a[1]]] });
    const rb = ST.relief.bbox, p0 = proj([rb[0], rb[3]]), p1 = proj([rb[2], rb[1]]);
    d3.select("#relief").attr("href", INLINE ? INLINE.relief : ST.relief.file)
      .attr("x", p0[0]).attr("y", p0[1]).attr("width", p1[0] - p0[0]).attr("height", p1[1] - p0[1]);
    snap = null; ["#states", "#evts", "#rings", "#arrows", "#leaders"].forEach(g => d3.select(g).selectAll("*").remove());
    render();
  }

  function drawStates(t) {
    const s = snapshot(t);
    if (s !== snap) {
      snap = s;
      const feats = SL.borders[String(s)];
      feats.forEach(f => { f.sa = f.properties.m ?? f.properties.a; });
      const sel = d3.select("#states").selectAll("path").data(feats, f => f.properties.n);
      sel.exit().remove();
      sel.enter().append("path").attr("class", "state").attr("d", path);
    }
    let fr = 0, co = 0, all = 0;
    d3.select("#states").selectAll("path").attr("class", f => {
      const b = bloc(f.properties.n, t); all += f.sa; if (b === "fr") fr += f.sa; else if (b === "co") co += f.sa;
      return "state " + b;
    });
    const pf = Math.round(100 * fr / all), pc = Math.round(100 * co / all);
    d3.select("#meter .fr").style("width", pf + "%"); d3.select("#meter .co").style("width", pc + "%");
    d3.select("#m-fr").text(`France & allies ${pf}%`); d3.select("#m-co").text(`Coalition ${pc}%`);
  }

  const line = d3.line().x(p => proj(p)[0]).y(p => proj(p)[1]).curve(d3.curveCatmullRom.alpha(.6));
  function drawArrows(t) {
    const hold = 60 * DAY, act = SL.ars.filter(a => t >= a.t0 && t < a.t1 + hold);
    const s = d3.select("#arrows").selectAll("path").data(act, a => a.n);
    s.exit().remove();
    s.enter().append("path").attr("class", "arrow");
    d3.select("#arrows").selectAll("path").attr("d", a => {
      const f = Math.min(1, (t - a.t0) / Math.max(DAY, a.t1 - a.t0));
      return line(a.pts.slice(0, Math.max(2, Math.ceil(a.pts.length * f))));
    }).style("opacity", a => t > a.t1 ? Math.max(0, 1 - (t - a.t1) / hold) : .85);
  }
  function drawEvents(t) {
    const vis = SL.evs.filter(e => e.t >= T0 && t >= e.t);
    const s = d3.select("#evts").selectAll("circle").data(vis, e => e.n);
    s.enter().append("circle").attr("class", "ev").attr("r", e => 2 + e.w * .9)
      .attr("cx", e => proj([e.lon, e.lat])[0]).attr("cy", e => proj([e.lon, e.lat])[1]);
    d3.select("#evts").selectAll("circle").classed("past", e => t - e.t > 90 * DAY);
    const live = beats.filter(b => t >= b.t && t < b.t + 50 * DAY);
    const r = d3.select("#rings").selectAll("circle").data(live, b => b.n);
    r.exit().remove();
    r.enter().append("circle").attr("class", "ring").attr("cx", b => proj([b.lon, b.lat])[0]).attr("cy", b => proj([b.lon, b.lat])[1]);
    d3.select("#rings").selectAll("circle").attr("r", b => 6 + 34 * Math.min(1, (t - b.t) / (50 * DAY)))
      .style("opacity", b => 1 - (t - b.t) / (50 * DAY));
  }
  function drawLeaders(t) {
    const on = ST.leadersC.filter(l => t >= l.t0 && t < l.t1);
    const s = d3.select("#leaders").selectAll("g").data(on, l => l.n + l.t0);
    s.exit().remove();
    const g = s.enter().append("g").attr("class", "leader").attr("transform", l => `translate(${proj([l.lon, l.lat])})`);
    g.append("circle").attr("r", 2.4);
    g.append("text").attr("y", -7).attr("font-size", innerWidth < 500 ? 11 : 13).text(l => l.n);
  }
  function render() {
    drawStates(T); drawArrows(T); drawEvents(T); drawLeaders(T);
    d3.select("#year").text(new Date(T).getUTCFullYear());
  }

  const MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function showCaption(b) {
    const c = d3.select("#caption"), D = new Date(b.t);
    c.classed("on", false);
    setTimeout(() => {
      c.html("").classed("on", true);
      c.append("small").text(`${MON[D.getUTCMonth()]} ${D.getUTCFullYear()} · ${b.n}`);
      c.append("span").text(b.text);
    }, 120);
  }
  function tick(now) {
    const dt = Math.min(100, now - last); last = now;
    if (phase === "travel") {
      if (now < dwellUntil) { requestAnimationFrame(tick); return; }
      const nt = T + TRAVEL_DAYS_PER_S * DAY * dt / 1000;
      const b = beats[nextBeat];
      if (b && nt >= b.t) {
        T = b.t; nextBeat++; dwellUntil = now + DWELL_MS; showCaption(b);
      } else T = Math.min(nt, T1);
      render();
      if (T >= T1 && nextBeat >= beats.length) { phase = "end"; setTimeout(finish, END_HOLD_MS + DWELL_MS); }
    }
    if (phase !== "end") requestAnimationFrame(tick);
  }
  function finish() {
    d3.select("#caption").classed("on", false);
    d3.select("#endcard").classed("on", true);
    window.__storyDone = true;
  }
  function play() {
    d3.select("#start").attr("hidden", true);
    d3.select("#endcard").classed("on", false);
    T = T0; nextBeat = 0; dwellUntil = 0; render();
    d3.select("#caption").classed("on", false);
    d3.select("#hook").classed("on", true);
    setTimeout(() => {
      d3.select("#hook").classed("on", false);
      phase = "travel"; last = performance.now(); requestAnimationFrame(tick);
    }, HOOK_MS);
  }

  load().then(([slice, story]) => {
    SL = slice; ST = story;
    SL.rulesC = SL.rules.map(r => [new RegExp(r[0]), r[1], d(r[2]), d(r[3])]);
    SL.evs = SL.events.map(e => ({ n: e[0], t: d(e[1]), lat: e[2], lon: e[3], w: e[6] }));
    SL.ars = SL.arrows.map(a => ({ n: a[0], t0: d(a[1]), t1: d(a[2]), pts: a[4].map(p => [p[1], p[0]]) }));
    T0 = d(ST.start); T1 = d(ST.end); T = T0;
    const vi = VOICE === "epic" ? 2 : 1;
    beats = ST.beats.map(b => { const e = SL.evs.find(x => x.n === b[0]); return { n: b[0].replace("Jena–Auerstedt", "Jena"), t: e.t, lat: e.lat, lon: e.lon, text: b[vi] }; })
      .sort((a, b) => a.t - b.t);
    ST.leadersC = ST.leaders.map(l => ({ n: l[0], lat: l[1], lon: l[2], t0: d(l[3]), t1: d(l[4]) }));
    d3.select("#hook p").text(ST.hook[VOICE]);
    d3.select("#endcard .line").text(ST.end_card);
    layout();
    let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(layout, 150); });
    d3.select("#start").on("click", play);
    d3.select("#replay").on("click", play);
    if (REC) setTimeout(play, 400);
  });
})();
