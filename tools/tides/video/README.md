# TIDES video

`render.py` turns a TIDES story (`docs/tides/story.html`) into a vertical 1080×1920 MP4 for Shorts, Reels and TikTok.

## How it works

The story player runs on the wall clock. That would make a screen capture choppy and different on every run. The renderer instead:

1. serves `docs/tides/` locally;
2. replaces the page's clock (`performance.now`, `Date.now`, `setTimeout`, `requestAnimationFrame` and CSS animations) with a virtual one;
3. advances that clock exactly 1/30 s per frame;
4. screenshots each frame and pipes it to ffmpeg.

The same story always produces the same file, byte for byte. The renderer also exits non-zero instead of producing a wrong video when:

- the story id is unknown (the player itself would silently fall back to the first story);
- the map never draws;
- the page throws an error;
- the story never reaches its end card.

## Setup (once)

Needs Python Playwright with Chromium, plus ffmpeg. The story fonts come from npm, because capture environments often cannot reach Google Fonts:

```sh
npm i @fontsource/cormorant-garamond@5 @fontsource/barlow-condensed@5 @fontsource/fraunces@5 \
      @fontsource/ibm-plex-mono@5 @fontsource/im-fell-english@5 @fontsource/im-fell-english-sc@5
```

## Render

```sh
python tools/tides/video/render.py napoleon napoleon.mp4                 # relief look, deadpan voice
python tools/tides/video/render.py americas americas.mp4 --voice epic
python tools/tides/video/render.py rome rome.mp4 --look paper
```

Run these from the folder that holds `node_modules`, or pass `--fonts <path>/node_modules/@fontsource`.

- **Stories:** `napoleon`, `rome`, `mongols`, `inca`, `americas`, `west-africa`
- **Looks:** `dark`, `paper`, `relief`
- **Voices:** `deadpan`, `epic`, `panel` (panel only where the story defines one)

A render takes about 2.5 minutes per 40 s of video.

## Not done yet

- Voiceover and music
- A watch-at URL on the end card
- Landscape 16:9 cuts
- Auto-publishing. Posting stays a human act.
