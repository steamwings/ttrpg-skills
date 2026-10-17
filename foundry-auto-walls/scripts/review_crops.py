#!/usr/bin/env python3
"""Labelled review crops of a walls.json over its map image (for Claude to Read and spot misses/junk).

  review_crops.py walls.json KEY image.webp x0,y0,x1,y1 NCOL NROW SCALE OUTPREFIX [--extra extra.json]

Draws red = wall, blue = door, cyan = window, magenta = edge; yellow dots = endpoints; tick labels every
100 image px on the top/left edges, so a crop pixel maps back with  X = crop_x0 + px/SCALE.
Writes OUTPREFIX-RC.png for each row/col of the box grid (each crop padded by 40px). `--extra` takes a
JSON list of [x0,y0,x1,y1] to highlight in green (candidates you're considering adding).
Typical: 3x3 crops at 0.75 for a 3000px building; then write the fixes for apply_fixes.py.
"""
import json, argparse
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
for a in ("walls", "key", "image", "box"): ap.add_argument(a)
ap.add_argument("ncol", type=int); ap.add_argument("nrow", type=int); ap.add_argument("scale", type=float); ap.add_argument("prefix")
ap.add_argument("--extra"); o = ap.parse_args()
W = json.load(open(o.walls))[o.key]
full = Image.open(o.image).convert("RGB"); d = ImageDraw.Draw(full)
col = {1: (255, 0, 0), 2: (0, 80, 255), 3: (0, 200, 255), 4: (255, 0, 255)}
for w in W: d.line(w[:4], fill=col.get(w[4], (0, 255, 0)), width=5)
if o.extra:
    for w in json.load(open(o.extra)): d.line(w[:4], fill=(0, 255, 0), width=9)
for w in W:
    for p in (w[:2], w[2:4]): d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=(255, 255, 0))
x0, y0, x1, y1 = map(int, o.box.split(",")); cw = (x1 - x0) // o.ncol; ch = (y1 - y0) // o.nrow
for r in range(o.nrow):
    for c in range(o.ncol):
        X0 = x0 + c * cw - 40; Y0 = y0 + r * ch - 40; X1 = X0 + cw + 80; Y1 = Y0 + ch + 80
        im = full.crop((X0, Y0, X1, Y1)); dd = ImageDraw.Draw(im)
        for gx in range((X0 // 100 + 1) * 100, X1, 100):
            dd.text((gx - X0 + 3, 3), str(gx), fill=(0, 0, 0)); dd.line([(gx - X0, 0), (gx - X0, 14)], fill=(0, 0, 0), width=3)
        for gy in range((Y0 // 100 + 1) * 100, Y1, 100):
            dd.text((3, gy - Y0 + 3), str(gy), fill=(0, 0, 0)); dd.line([(0, gy - Y0), (14, gy - Y0)], fill=(0, 0, 0), width=3)
        im.resize((int(im.width * o.scale), int(im.height * o.scale))).save(f"{o.prefix}-{r}{c}.png")
        print(f"{o.prefix}-{r}{c}.png  crop origin ({X0},{Y0})")
