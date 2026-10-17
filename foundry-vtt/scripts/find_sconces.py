#!/usr/bin/env python3
"""Find the small glowing light markers that many book maps draw (red/orange sconce dots on the
Witchlight maps: Motherhorn) and return them as light positions.

  find_sconces.py --out sconces.json L1=floor1.webp L2=floor2.webp [--drop-x-above L2=3150]

Rules: saturated red blob (R>140, R-G>70, R-B>60), 6-30 px, roughly round, fill > 0.35.
Dense clusters (>=2 neighbours within 45 px) are dropped: those are seats and upholstery, not lamps.
Pairs closer than 25 px are merged. Check the overlay (sconces-KEY.png) and drop map-furniture
false positives (compass rose, legend art) with --drop-x-above / by hand.
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import cKDTree


def find(path):
    a = np.array(Image.open(path).convert("RGBA")).astype(int)
    R, G, B, A = (a[..., i] for i in range(4))
    m = ndi.binary_closing((A > 0) & (R > 140) & (R - G > 70) & (R - B > 60), np.ones((3, 3)))
    lab, _ = ndi.label(m)
    pts = []
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        c = (lab[sl] == j).sum()
        if 6 <= h <= 30 and 6 <= w <= 30 and c >= 25 and 0.6 < h / w < 1.6 and c / (h * w) > 0.35:
            ys, xs = np.nonzero(lab[sl] == j)
            pts.append([int(xs.mean() + sl[1].start), int(ys.mean() + sl[0].start)])
    if not pts:
        return pts
    P = np.array(pts); t = cKDTree(P)
    keep = [p.tolist() for p in P if len(t.query_ball_point(p, 45)) - 1 < 2]
    out = []
    for p in keep:
        if not any(np.hypot(p[0] - q[0], p[1] - q[1]) < 25 for q in out):
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+"); ap.add_argument("--out", default="sconces.json")
    ap.add_argument("--drop-x-above", action="append", default=[])
    a = ap.parse_args()
    cut = {k: int(v) for k, v in (s.split("=") for s in a.drop_x_above)}
    res = {}
    for spec in a.images:
        k, _, p = spec.partition("=")
        pts = [q for q in find(p) if q[0] <= cut.get(k, 10 ** 9)]
        res[k] = pts
        im = Image.open(p).convert("RGB"); d = ImageDraw.Draw(im)
        for x, y in pts:
            d.ellipse([x - 22, y - 22, x + 22, y + 22], outline=(0, 255, 0), width=6)
        im.save(os.path.join(os.path.dirname(os.path.abspath(a.out)), f"sconces-{k}.png"))
        print(k, len(pts))
    json.dump(res, open(a.out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
