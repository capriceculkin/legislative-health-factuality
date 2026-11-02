"""edu_figure_files.py OUT_DIR EDU_OUT.json [MORE.json ...] [--rows sample|1,test|A8|fr,sample|58] [--all]

The "tree inside a tree" figure for each chosen sentence as its own file, for GitHub and for slides: the discourse
relations drawn the Mann and Thompson way on top, and each unit's own constituency tree underneath (edu_draw.figure,
simple=True). Reads the records edu_pipeline.py writes, so no parser is needed.

Always writes OUT_DIR/<id>.svg (GitHub shows SVG directly, and it stays sharp at any size). Also writes
OUT_DIR/<id>.png with the first converter it finds: playwright, cairosvg, rsvg-convert, or qlmanage (built into macOS).
    python3 scripts/v6/edu_figure_files.py docs/figures outputs/edu/edu_reparsed.json outputs/edu/more_reparsed.json"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edu_draw as DRAW  # noqa: E402

FLOWS = "sample|1,test|A8|fr,sample|58"        # the three sentences on the workbook's flow tabs

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("records", nargs="+")
ap.add_argument("--rows", default=FLOWS)
ap.add_argument("--all", action="store_true", help="every sentence in the records, not only --rows")
ap.add_argument("--sets", default="", help="every sentence in these sets, e.g. sample,heldout,more (the real sentences)")
A = ap.parse_args()

recs = {}
for f in A.records:
    for r in json.load(open(f, encoding="utf-8"))["rows"]:
        recs[r["n"]] = r
if A.sets:
    want = [n for n in recs if n.split("|")[0] in A.sets.split(",")]
    missing = []
else:
    want = list(recs) if A.all else [n for n in A.rows.split(",") if n in recs]
    missing = [n for n in A.rows.split(",") if n not in recs] if not A.all else []
out = Path(A.out)
out.mkdir(parents=True, exist_ok=True)


def name(n):
    return n.replace("|", "_")


svgs = {}
for n in want:
    p = out / (name(n) + ".svg")
    p.write_text(DRAW.figure(recs[n], simple=True), encoding="utf-8")
    svgs[n] = p
print(f"wrote {len(svgs)} SVG figures to {out}/" + (f"  (not in the records, skipped: {', '.join(missing)})" if missing else ""))


def with_playwright():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(device_scale_factor=2)
        for n, p in svgs.items():
            pg.set_content(f'<html><body style="margin:0;background:#fff">{p.read_text(encoding="utf-8")}</body></html>')
            pg.query_selector("svg").screenshot(path=str(p.with_suffix(".png")))
        br.close()


def with_cairosvg():
    import cairosvg
    for p in svgs.values():
        cairosvg.svg2png(url=str(p), write_to=str(p.with_suffix(".png")), scale=2, background_color="white")


def with_rsvg():
    for p in svgs.values():
        subprocess.run(["rsvg-convert", "-z", "2", "-b", "white", "-o", str(p.with_suffix(".png")), str(p)], check=True)


def with_qlmanage():
    "macOS Quick Look: renders an SVG to PNG with nothing to install."
    for p in svgs.values():
        w = int(float(p.read_text(encoding="utf-8").split('width="', 1)[1].split('"', 1)[0]))
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["qlmanage", "-t", "-s", str(2 * w), "-o", d, str(p)], check=True, capture_output=True)
            made = Path(d) / (p.name + ".png")
            if not made.exists():
                raise RuntimeError("qlmanage made no PNG")
            shutil.move(str(made), str(p.with_suffix(".png")))


done = None
for label, fn, ok in (("playwright", with_playwright, True), ("cairosvg", with_cairosvg, True),
                      ("rsvg-convert", with_rsvg, shutil.which("rsvg-convert") is not None),
                      ("qlmanage", with_qlmanage, shutil.which("qlmanage") is not None)):
    if not ok or not svgs:
        continue
    try:
        fn()
        done = label
        break
    except Exception as ex:                    # noqa: BLE001   try the next converter
        print(f"   {label} could not make the PNGs ({type(ex).__name__}); trying the next one")
bad = []
if done:                                       # a PNG must keep the figure's shape; a cropped or squashed one is removed
    try:
        from PIL import Image
        for n, p in svgs.items():
            t = p.read_text(encoding="utf-8")
            w = float(t.split('width="', 1)[1].split('"', 1)[0]); h = float(t.split('height="', 1)[1].split('"', 1)[0])
            with Image.open(p.with_suffix(".png")) as im:
                if abs(im.width / im.height - w / h) > 0.03 * (w / h):
                    bad.append(n)
            if n in bad:
                p.with_suffix(".png").unlink()
    except ImportError:
        pass
print(f"wrote {len(svgs) - len(bad)} PNG figures with {done}" + (f"; removed {len(bad)} that came out the wrong shape: {', '.join(bad)}" if bad else "")
      if done else "   no PNG converter found: the SVGs are written, and they open in any browser")
