#!/usr/bin/env python3
"""Render a TIDES story to MP4, deterministically.

The story player (docs/tides/story.html) runs on the wall clock. This script
replaces the page's clock with a virtual one, advances it exactly 1/FPS second
per frame, screenshots each frame and pipes the frames to ffmpeg. The same
inputs therefore always produce the same frame count, whatever the machine speed.

    python tools/tides/video/render.py napoleon out.mp4
    python tools/tides/video/render.py rome out.mp4 --look relief --voice epic

Needs: playwright (Python), Chromium, ffmpeg, and the story fonts installed
from npm (see README.md). Exits non-zero on any failure; it never writes a
video for a story that does not exist or a map that did not draw.
"""
import argparse, functools, http.server, json, pathlib, socketserver, subprocess, sys, threading

ROOT = pathlib.Path(__file__).resolve().parents[3]
SITE = ROOT / "docs" / "tides"

# Google Fonts families used by story.css -> fontsource package, weights, styles.
FONTS = {
    "Cormorant Garamond": ("cormorant-garamond", [500, 700], ["normal"]),
    "Barlow Condensed": ("barlow-condensed", [500, 700], ["normal"]),
    "Fraunces": ("fraunces", [300, 600], ["normal"]),
    "IBM Plex Mono": ("ibm-plex-mono", [400, 500], ["normal"]),
    "IM Fell English": ("im-fell-english", [400], ["normal", "italic"]),
    "IM Fell English SC": ("im-fell-english-sc", [400], ["normal"]),
}

CLOCK = r"""
(() => {
  let now = 0, tid = 1, timers = [], raf = [];
  const D0 = Date.UTC(2026, 0, 1);
  performance.now = () => now;
  Date.now = () => D0 + now;
  window.requestAnimationFrame = cb => { raf.push(cb); return raf.length; };
  window.cancelAnimationFrame = () => {};
  window.setTimeout = (cb, ms = 0, ...a) => { const id = tid++; timers.push({ id, at: now + (+ms || 0), cb, a }); return id; };
  window.clearTimeout = id => { timers = timers.filter(t => t.id !== id); };
  window.setInterval = () => { throw new Error("setInterval not virtualised"); };
  window.__advance = dt => {
    const target = now + dt;
    for (;;) {
      timers.sort((x, y) => x.at - y.at || x.id - y.id);
      const t = timers[0];
      if (!t || t.at > target) break;
      timers.shift(); now = t.at; t.cb(...t.a);
    }
    now = target;
    raf.splice(0).forEach(cb => cb(now));
    for (const an of document.getAnimations()) {
      if (an.__v === undefined) { an.__v = 1; an.pause(); an.currentTime = 0; }
      else an.currentTime = (an.currentTime || 0) + dt;
    }
  };
})();
"""


def die(msg):
    print(f"render: FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def font_css(fontdir):
    rules = []
    for fam, (pkg, weights, styles) in FONTS.items():
        for w in weights:
            for s in styles:
                f = fontdir / pkg / "files" / f"{pkg}-latin-{w}-{s}.woff2"
                if not f.exists():
                    die(f"font file missing: {f} (run the npm install in README.md)")
                rules.append(f"@font-face{{font-family:'{fam}';font-style:{s};font-weight:{w};"
                             f"font-display:block;src:url(https://fonts.local/{pkg}/{f.name}) format('woff2')}}")
    return "\n".join(rules)


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", help="story id from docs/tides/data/stories.json")
    ap.add_argument("out", help="output .mp4 path")
    ap.add_argument("--look", default="relief", choices=["dark", "paper", "relief"])
    ap.add_argument("--voice", default="deadpan", choices=["deadpan", "epic", "panel"])
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=540, help="CSS px; output is 2x")
    ap.add_argument("--height", type=int, default=960, help="CSS px; output is 2x")
    ap.add_argument("--tail", type=float, default=3.0, help="seconds to hold the end card")
    ap.add_argument("--max-seconds", type=float, default=120)
    ap.add_argument("--fonts", default=str(pathlib.Path.cwd() / "node_modules" / "@fontsource"))
    a = ap.parse_args()

    # Fail loudly on an unknown story. The player itself silently falls back to the
    # first story, which is exactly the wrong-video failure this check exists to stop.
    ids = [s["id"] for s in json.loads((SITE / "data" / "stories.json").read_text())["stories"]]
    if a.story not in ids:
        die(f"unknown story '{a.story}'. Known: {', '.join(ids)}")
    story = json.loads((SITE / "data" / f"story-{a.story}.json").read_text())
    if a.voice == "panel" and not story.get("panel"):
        die(f"story '{a.story}' has no panel voice")

    css = font_css(pathlib.Path(a.fonts))
    from playwright.sync_api import sync_playwright

    srv = serve(SITE)
    url = f"http://127.0.0.1:{srv.server_address[1]}/story.html#{a.story}.{a.look}.{a.voice}.rec"
    dt = 1000 / a.fps
    W, H = a.width * 2, a.height * 2
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(a.fps),
         "-i", "-", "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
         "-crf", "18", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    frames = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=2)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def fonts(route):
            u = route.request.url
            if "fonts.googleapis.com" in u:
                return route.fulfill(status=200, content_type="text/css", body=css)
            pkg, name = u.split("fonts.local/")[1].split("/", 1)
            route.fulfill(status=200, content_type="font/woff2",
                          body=(pathlib.Path(a.fonts) / pkg / "files" / name).read_bytes())
        pg.route("https://fonts.googleapis.com/**", fonts)
        pg.route("https://fonts.local/**", fonts)
        pg.add_init_script(CLOCK)
        pg.goto(url, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        try:
            pg.wait_for_function("document.querySelectorAll('#states path').length > 0", timeout=15000)
        except Exception:
            die(f"map never drew for '{a.story}'. Page errors: {errors or 'none'}")
        if errors:
            die(f"page errors before render: {errors}")
        # Wait for the relief image to decode so frame 1 is not missing terrain.
        pg.wait_for_function("(() => { const i = new Image(); i.src = document.querySelector('#relief').getAttribute('href'); return i.decode().then(() => true, () => true); })()")

        done_at = None
        limit = int(a.max_seconds * a.fps)
        while frames < limit:
            pg.evaluate(f"window.__advance({dt})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=94))
            frames += 1
            if done_at is None and pg.evaluate("!!window.__storyDone"):
                done_at = frames
            if done_at is not None and frames - done_at >= a.tail * a.fps:
                break
        b.close()
    srv.shutdown()
    ff.stdin.close()
    if ff.wait() != 0:
        die("ffmpeg failed")
    if errors:
        die(f"page errors during render: {errors}")
    if done_at is None:
        die(f"story did not finish within {a.max_seconds}s")
    print(json.dumps({"story": a.story, "look": a.look, "voice": a.voice, "fps": a.fps,
                      "frames": frames, "seconds": round(frames / a.fps, 2), "size": f"{W}x{H}", "out": str(out)}))


if __name__ == "__main__":
    main()
