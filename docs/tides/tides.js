/* TIDES — a reusable engine for animated sovereign-scale historical maps.
 * A slice is pure data (docs/tides/data/<id>.json, built by tools/tides/build_slices.py):
 * border snapshots, dated status rules, events, campaign arrows, eras, and a source
 * title on every row. Adding a region means adding a slice file, not changing this code.
 */
(function () {
  "use strict";
  const DAY = 86400000;
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const INLINE = window.TIDES_INLINE || null; // single-file preview build embeds the data here
  const TT = window.TIDES_TIME, d = TT.parse;
  const fmt = s => TT.label(s, S && S.bc);
  const wiki = t => "https://en.wikipedia.org/wiki/" + encodeURIComponent(t.replace(/ /g, "_"));
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  const W = () => innerWidth, H = () => innerHeight;
  const svg = d3.select("svg"), view = d3.select("#view");
  let proj = d3.geoMercator(), path = d3.geoPath(proj);
  let S = null, T = 0, T0 = 0, T1 = 1, playing = false, speed = 1, last = 0, snap = null, started = false;
  const SP = [1, 2, 4];
  const cache = {};

  const zoom = d3.zoom().scaleExtent([.6, 14]).on("zoom", e => {
    view.attr("transform", e.transform);
    const k = Math.sqrt(e.transform.k);
    d3.selectAll(".ev").attr("r", function () { return +this.dataset.r / k; });
    d3.selectAll(".lbl").attr("font-size", 10 / k);
  });
  svg.call(zoom);
  const kNow = () => Math.sqrt(d3.zoomTransform(svg.node()).k);

  // ---------- slice loading ----------
  async function manifest() {
    if (INLINE) return INLINE.manifest;
    const r = await fetch("data/slices.json"); return (await r.json()).slices;
  }
  async function loadSlice(m) {
    if (cache[m.id]) return cache[m.id];
    const raw = INLINE ? INLINE.data[m.id] : await (await fetch(m.file)).json();
    const s = Object.assign({}, raw);
    s.t0 = d(raw.start); s.t1 = d(raw.end); s.bc = raw.start[0] === "-";
    s.rulesC = raw.rules.map(r => [new RegExp(r[0]), r[1], d(r[2]), d(r[3]), r[4]]);
    s.erasC = raw.eras.map(e => [d(e[0]), e[1]]);
    s.evs = raw.events.map(e => ({ n: e[0], ds: e[1], t: d(e[1]), lat: e[2], lon: e[3], sides: e[4], res: e[5], w: e[6], src: e[7] }));
    s.ars = raw.arrows.map(a => ({ n: a[0], t0: d(a[1]), t1: d(a[2]), k: a[3], pts: a[4].map(p => [p[1], p[0]]), src: a[5] }));
    s.snaps = raw.snapshots.map(x => ({ year: x.year, from: d(x.from), source: x.source })).sort((a, b) => a.from - b.from);
    const span = (s.t1 - s.t0) / DAY;
    s.cruise = span / 95; s.near = s.cruise / 5; // ~95 s end to end at 1x, slower around events
    cache[m.id] = s; return s;
  }

  // ---------- state ----------
  function snapshot(t) { let y = S.snaps[0].year; for (const x of S.snaps) if (t >= x.from) y = x.year; return y; }
  function bloc(name, t) { for (const r of S.rulesC) if (r[0].test(name) && t >= r[2] && t < r[3]) return r[1]; return S.default_bloc; }
  function rule(name, t) { for (const r of S.rulesC) if (r[0].test(name) && t >= r[2] && t < r[3]) return r; return null; }
  // A bloc marked "hatch" (e.g. a war of independence) is drawn as stripes over its base colour,
  // so it never relies on hue alone to stand apart from its neighbours.
  const color = b => { const v = S.blocs[b] || S.blocs[S.default_bloc]; return v[2] === "hatch" ? `url(#hatch-${b})` : v[1]; };
  function hatchDefs() {
    d3.select("svg defs").remove();
    const defs = svg.insert("defs", ":first-child");
    for (const [k, v] of Object.entries(S.blocs)) {
      if (v[2] !== "hatch") continue;
      const p = defs.append("pattern").attr("id", "hatch-" + k).attr("patternUnits", "userSpaceOnUse")
        .attr("width", 6).attr("height", 6).attr("patternTransform", "rotate(45)");
      p.append("rect").attr("width", 6).attr("height", 6).attr("fill", v[1]);
      p.append("rect").attr("width", 2.6).attr("height", 6).attr("fill", "#14171f");
    }
  }
  const swatch = v => v[2] === "hatch" ? `repeating-linear-gradient(45deg,${v[1]} 0 3px,#14171f 3px 5px)` : v[1];

  function drawStates(t) {
    const s = snapshot(t);
    if (s !== snap) {
      snap = s;
      const feats = S.borders[String(s)];
      const sel = d3.select("#states").selectAll("path").data(feats, f => f.properties.n);
      sel.exit().transition().duration(700).style("opacity", 0).remove();
      sel.enter().append("path").attr("class", "state").style("opacity", 0).attr("d", path)
        .style("fill", f => color(bloc(f.properties.n, t)))
        .on("mousemove", (e, f) => showTip(e, stateTip(f)))
        .on("mouseleave", hideTip)
        .on("click", (e, f) => { e.stopPropagation(); showTip(e, stateTip(f), true); })
        .transition().duration(700).style("opacity", 1);
      sel.attr("d", path);
      const big = feats.filter(f => f.properties.a > S.labelMin && !/culture|hunter-gatherers|nomads|tribes|minor states/i.test(f.properties.n)).sort((a, b) => b.properties.a - a.properties.a).slice(0, W() < 640 ? 7 : 14);
      const lab = d3.select("#labels").selectAll("text").data(big, f => f.properties.n);
      lab.exit().remove();
      lab.enter().append("text").attr("class", "lbl").attr("font-size", 10 / kNow()).merge(lab)
        .attr("transform", f => `translate(${path.centroid(f)})`).text(f => shortName(f.properties.n));
    }
    const present = new Set();
    d3.select("#states").selectAll("path").style("fill", f => { const b = bloc(f.properties.n, t); present.add(b); return color(b); });
    d3.selectAll("#legend span[data-b]").style("display", function () { return present.has(this.dataset.b) ? null : "none"; });
  }
  function shortName(n) {
    return n.replace("United Kingdom of Great Britain and Ireland", "Britain").replace(/^UK$/, "Britain")
      .replace(/^Viceroyalty of (the )?/, "").replace("United Provinces of the ", "").replace("Kingdom of the ", "");
  }
  function stateTip(f) {
    const n = f.properties.n, r = rule(n, T), b = bloc(n, T);
    return `<b>${esc(n)}</b><br><i>${esc(S.blocs[b][0])}</i>` +
      (r ? `<br><a href="${wiki(r[4])}" target="_blank" rel="noopener">source: ${esc(r[4])} ↗</a>` : "") +
      `<br><span class="m">border: basemap ${snap < 0 ? -snap + " BC" : snap}</span>`;
  }

  const line = d3.line().x(p => proj(p)[0]).y(p => proj(p)[1]).curve(d3.curveCatmullRom.alpha(.6));
  function drawArrows(t) {
    const hold = 45 * DAY, act = S.ars.filter(a => t >= a.t0 && t < a.t1 + hold);
    const s = d3.select("#arrows").selectAll("path").data(act, a => a.n);
    s.exit().transition().duration(600).style("opacity", 0).remove();
    s.enter().append("path").attr("class", a => "arrow " + ((S.arrow_kinds[a.k] || [])[1] || ""))
      .style("stroke", a => (S.arrow_kinds[a.k] || ["#ccc"])[0]).style("opacity", 0)
      .transition().duration(400).style("opacity", 1);
    d3.select("#arrows").selectAll("path").attr("d", a => {
      const f = Math.min(1, (t - a.t0) / Math.max(DAY, a.t1 - a.t0));
      const n = Math.max(2, Math.ceil(a.pts.length * f)); return line(a.pts.slice(0, n));
    }).style("opacity", a => t > a.t1 ? Math.max(0, 1 - (t - a.t1) / hold) : 1);
  }
  function evHtml(ev, links) {
    return `<b>${esc(ev.n)}</b>${fmt(ev.ds)} · ${esc(ev.sides)}<br><i>${esc(ev.res)}</i>` +
      (links ? `<br><a href="${wiki(ev.src)}" target="_blank" rel="noopener">source: ${esc(ev.src)} ↗</a>` : "");
  }
  function drawEvents(t) {
    const vis = S.evs.filter(e => t >= e.t);
    const s = d3.select("#evts").selectAll("circle").data(vis, e => e.n + e.ds);
    s.enter().append("circle").attr("class", "ev")
      .attr("cx", e => proj([e.lon, e.lat])[0]).attr("cy", e => proj([e.lon, e.lat])[1])
      .attr("data-r", e => 1.6 + e.w * .7).attr("r", 0)
      .on("mousemove", (e, ev) => showTip(e, evHtml(ev, true)))
      .on("mouseleave", hideTip)
      .on("click", (e, ev) => { e.stopPropagation(); showTip(e, evHtml(ev, true), true); })
      .transition().duration(300).attr("r", function () { return +this.dataset.r / kNow(); });
    s.exit().remove();
    d3.select("#evts").selectAll("circle").attr("class", e => "ev" + (t - e.t > 60 * DAY ? " past" : ""));
    const live = S.evs.filter(e => t >= e.t && t < e.t + 40 * DAY);
    const r = d3.select("#rings").selectAll("circle").data(live, e => e.n + e.ds);
    r.exit().remove();
    r.enter().append("circle").attr("class", "ring").attr("cx", e => proj([e.lon, e.lat])[0]).attr("cy", e => proj([e.lon, e.lat])[1]);
    d3.select("#rings").selectAll("circle")
      .attr("r", e => (3 + e.w * 4) * ((t - e.t) / (40 * DAY)) * 2.2 / kNow())
      .style("opacity", e => 1 - (t - e.t) / (40 * DAY));
    const recent = S.evs.filter(e => t >= e.t && t < e.t + 200 * DAY).slice(-3).reverse();
    const tk = d3.select("#ticker").selectAll(".card").data(recent, e => e.n + e.ds);
    tk.exit().remove();
    tk.enter().append("div").attr("class", "card").html(e => evHtml(e, false));
    d3.select("#ticker").selectAll(".card").sort((a, b) => b.t - a.t);
  }
  function hud(t) {
    const D = new Date(t);
    const y = TT.year(t, S.bc);
    d3.select("#year").text(y);
    d3.select("#date").text(`${D.getUTCDate()} ${MON[D.getUTCMonth()]} ${y}`);
    let era = ""; for (const e of S.erasC) if (t >= e[0]) era = e[1];
    d3.select("#era").text(era);
  }
  function render() {
    drawStates(T); drawArrows(T); drawEvents(T); hud(T);
    d3.select("#t").property("value", Math.round((T - T0) / DAY));
  }

  // ---------- tooltip ----------
  function showTip(e, html, pin) {
    const q = d3.select("#tip").style("display", "block").classed("pinned", !!pin).html(html), n = q.node();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + n.offsetWidth > W()) x = Math.max(8, e.clientX - n.offsetWidth - 10);
    if (y + n.offsetHeight > H()) y = Math.max(8, e.clientY - n.offsetHeight - 10);
    q.style("left", x + "px").style("top", y + "px");
  }
  function hideTip() { if (!d3.select("#tip").classed("pinned")) d3.select("#tip").style("display", "none"); }
  svg.on("click", () => d3.select("#tip").classed("pinned", false).style("display", "none"));

  // ---------- clock ----------
  function rate(t) {
    const near = S.evs.some(e => Math.abs(e.t - t) < 30 * DAY) || S.ars.some(a => t >= a.t0 && t < a.t1);
    return (near ? S.near : S.cruise) * speed;
  }
  function tick(now) {
    if (!playing) return;
    const dt = Math.min(.1, (now - last) / 1000); last = now;
    T += rate(T) * dt * DAY;
    if (T >= T1) { T = T1; setPlaying(false); d3.select("#play").text("▶ Replay"); }
    render();
    if (playing) requestAnimationFrame(tick);
  }
  function setPlaying(p) {
    playing = p;
    d3.select("#play").text(p ? "❚❚ Pause" : "▶ Play").classed("on", p);
    if (p) { hideIntro(); last = performance.now(); requestAnimationFrame(tick); }
  }
  function hideIntro() { d3.select("#intro").classed("show", false); started = true; }

  // ---------- layout ----------
  function barH() { return document.getElementById("bar").offsetHeight; }
  function baseFit() {
    const v = S.views[0];
    proj.fitExtent([[20, 90], [W() - 20, H() - barH() - 10]],
      { type: "MultiPoint", coordinates: [v[2], v[3], [v[2][0], v[3][1]], [v[3][0], v[2][1]]] });
  }
  function fit(key, anim) {
    const v = S.views.find(x => x[0] === key) || S.views[0];
    const g = { type: "MultiPoint", coordinates: [v[2], v[3], [v[2][0], v[3][1]], [v[3][0], v[2][1]]] };
    const b = path.bounds(g), dx = b[1][0] - b[0][0], dy = b[1][1] - b[0][1];
    const top = 90, bottom = H() - barH() - 10, k = Math.min((W() - 30) / dx, (bottom - top) / dy) * .96;
    const tx = W() / 2 - k * (b[0][0] + b[1][0]) / 2, ty = (top + bottom) / 2 - k * (b[0][1] + b[1][1]) / 2;
    (anim ? svg.transition().duration(1000) : svg).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
  }
  function layout() {
    if (!S) return;
    if (W() < 640) d3.select("#ticker").style("bottom", barH() + 8 + "px");
    baseFit(); snap = null;
    ["#states", "#labels", "#evts", "#rings", "#arrows"].forEach(g => d3.select(g).selectAll("*").remove());
    render();
    fit(d3.select("#views button.on").attr("data-v") || S.views[0][0], false);
  }

  // ---------- UI ----------
  function buildUi() {
    d3.select("#sub").text(`${S.title} · ${S.period}`);
    d3.select("#i-kicker").text(`${S.title} · ${S.period}`);
    d3.select("#i-title").text(S.tagline);
    d3.select("#i-text").text(S.intro);
    d3.select("#bigplay").text(`▶ Play ${S.period}`);
    d3.select("#views").selectAll("button").remove();
    d3.select("#views").selectAll("button").data(S.views).enter().append("button").attr("data-v", v => v[0]).text(v => v[1])
      .on("click", function () { d3.selectAll("#views button").classed("on", false); d3.select(this).classed("on", true); fit(this.dataset.v, true); });
    d3.selectAll("#views button").classed("on", (v, i) => i === 0);
    const used = new Set(S.rules.map(r => r[1]));
    const items = Object.entries(S.blocs).filter(([k]) => used.has(k) || k === S.default_bloc);
    d3.select("#legend").html(items.map(([k, v]) => `<span data-b="${k}" style="--c:${swatch(v)}">${esc(v[0])}</span>`).join("") +
      `<span class="b" style="--c:var(--gold)">Event</span>`);
    d3.select("#t").attr("max", Math.round((T1 - T0) / DAY));
    d3.select("#srcbody").html(sourcesHtml());
  }
  function sourcesHtml() {
    const snaps = S.snaps.map(x => `<li>${x.year < 0 ? -x.year + " BC" : x.year} borders (used from ${TT.year(x.from, S.bc)}): <a href="${x.source.url}" target="_blank" rel="noopener">${esc(x.source.repo)}/${esc(x.source.file)}</a> <span class="m">@${x.source.commit.slice(0, 7)} · ${x.source.license}</span></li>`).join("");
    const evs = S.evs.map(e => `<li>${fmt(e.ds)} — ${esc(e.n)}: <a href="${wiki(e.src)}" target="_blank" rel="noopener">${esc(e.src)}</a></li>`).join("");
    const ars = S.ars.map(a => `<li>${esc(a.n)}: <a href="${wiki(a.src)}" target="_blank" rel="noopener">${esc(a.src)}</a></li>`).join("");
    const seen = new Set(), rules = S.rules.filter(r => !seen.has(r[4]) && seen.add(r[4]))
      .map(r => `<li><a href="${wiki(r[4])}" target="_blank" rel="noopener">${esc(r[4])}</a></li>`).join("");
    return `<p class="m">Sovereign-scale only. Borders are snapshots from the historical-basemaps project; between snapshots, each state is tinted by dated status rules. Event positions are approximate to the battle or city. Names follow the basemap's contemporary labels.</p>
      <h3>Border snapshots</h3><ul>${snaps}</ul><h3>Events (${S.evs.length})</h3><ul>${evs}</ul>
      <h3>Campaigns</h3><ul>${ars}</ul><h3>Status rules cite</h3><ul>${rules}</ul>`;
  }

  async function selectSlice(m, fromHash) {
    setPlaying(false);
    S = await loadSlice(m);
    S.labelMin = S.label_min ?? 4;
    T0 = S.t0; T1 = S.t1; T = T0;
    proj = S.projection === "naturalEarth" ? d3.geoNaturalEarth1() : d3.geoMercator();
    path = d3.geoPath(proj);
    d3.selectAll("#slices button").classed("on", b => b.id === m.id);
    if (!fromHash) history.replaceState(null, "", "#" + m.id);
    hatchDefs();
    buildUi();
    d3.select("#tip").classed("pinned", false).style("display", "none");
    d3.select("#ticker").selectAll("*").remove();
    d3.select("#intro").classed("show", true);
    requestAnimationFrame(layout);
  }

  async function init() {
    const list = await manifest();
    d3.select("#slices").selectAll("button").data(list).enter().append("button").attr("role", "tab")
      .html(m => `${esc(m.title)}<span class="p">${esc(m.period)}</span>`)
      .on("click", (e, m) => selectSlice(m));
    d3.select("#play").on("click", () => { if (T >= T1) T = T0; setPlaying(!playing); });
    d3.select("#bigplay").on("click", () => { if (T >= T1) T = T0; setPlaying(true); });
    d3.select("#spd").on("click", function () { speed = SP[(SP.indexOf(speed) + 1) % SP.length]; d3.select(this).text(speed + "×"); });
    d3.select("#rst").on("click", () => { setPlaying(false); T = T0; render(); });
    d3.select("#t").on("input", function () { hideIntro(); T = T0 + (+this.value) * DAY; render(); });
    d3.select("#src").on("click", () => d3.select("#srcpanel").classed("open", true));
    d3.select("#srcclose").on("click", () => d3.select("#srcpanel").classed("open", false));
    addEventListener("keydown", e => { if (e.code === "Space") { e.preventDefault(); d3.select("#play").dispatch("click"); } });
    let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(layout, 120); });
    addEventListener("hashchange", () => { const m = list.find(x => x.id === location.hash.slice(1)); if (m && (!S || m.id !== S.id)) selectSlice(m, true); });
    const first = list.find(x => x.id === location.hash.slice(1)) || list[0];
    await selectSlice(first, true);
  }
  init();
})();
