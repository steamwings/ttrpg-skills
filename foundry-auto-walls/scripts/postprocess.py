#!/usr/bin/env python3
"""Post-process a walls.json against the map image:

  postprocess.py walls.json --out walls2.json L1=floor1.webp[:x0,y0,x1,y1] L2=...  [--no-markers] [--no-rings]

1. MARKERS: map-key ovals (white ellipse with a black silhouette, ~110x135px at 100px/square) and their pure-white
   callout triangles produce tangles of junk walls. Detect them, delete kind-1 walls inside, then reconnect a
   straight wall the marker was sitting on (dead ends facing each other across the marker, same row/column).
2. RINGS: round rooms/towers whose outline was only partly detected. Hough circles (r 100..420) validated by
   >= ring_dark fraction of dark pixels along the circle; pieces of the circle not already covered by a wall
   (within 14px) and not crossing a door/window are added as kind-1 walls. Optional box limits the search.
"""
import argparse, json, math
import numpy as np, cv2
from PIL import Image
from scipy import ndimage as ndi


def seg_dist(p, s):
    A = np.array(s[:2], float); B = np.array(s[2:4], float); P = np.array(p, float); AB = B - A; L2 = AB @ AB
    u = 0 if L2 == 0 else np.clip((P - A) @ AB / L2, 0, 1)
    return np.linalg.norm(A + u * AB - P)


def find_markers(a):
    wh = (a.min(-1) > 225).astype(np.uint8)
    pure = a.min(-1) > 232
    n, lab, st, _ = cv2.connectedComponentsWithStats(wh, 8)
    zone = np.zeros(wh.shape, bool); found = []
    P = 220   # work in a window around each candidate
    for j in range(1, n):
        x, y, w, h, area = st[j]
        if not (90 <= w <= 130 and 115 <= h <= 150 and area > 2500):
            continue
        comp = lab[y:y + h, x:x + w] == j
        filled = ndi.binary_fill_holes(comp)
        if not (0.75 < filled.sum() / (math.pi * w * h / 4) < 1.15 and (filled.sum() - comp.sum()) / filled.sum() > 0.15):
            continue
        found.append([int(x + w / 2), int(y + h / 2), int(w / 2), int(h / 2)])
        X0, Y0 = max(x - P, 0), max(y - P, 0); X1, Y1 = min(x + w + P, wh.shape[1]), min(y + h + P, wh.shape[0])
        z = np.zeros((Y1 - Y0, X1 - X0), bool); z[y - Y0:y - Y0 + h, x - X0:x - X0 + w] = filled
        z = ndi.binary_dilation(z, iterations=14)
        pw = pure[Y0:Y1, X0:X1]; plab, _ = ndi.label(pw)
        for t in np.unique(plab[ndi.binary_dilation(z, iterations=10) & pw]):
            if t == 0: continue
            tm = plab == t
            if tm.sum() < 12000:
                z |= ndi.binary_dilation(tm, iterations=8)
        # convex hull of oval + callout triangle, padded: the triangle's tip at the door leaves junk too
        ys_, xs_ = np.nonzero(z)
        hull = cv2.convexHull(np.stack([xs_, ys_], 1).astype(np.int32))
        hz = np.zeros(z.shape, np.uint8); cv2.fillPoly(hz, [hull], 1)
        z |= ndi.binary_dilation(hz.astype(bool), iterations=12)
        zone[Y0:Y1, X0:X1] |= z
    return found, zone


def degree(segs):
    d = {}
    for s in segs:
        for p in ((s[0], s[1]), (s[2], s[3])): d[p] = d.get(p, 0) + 1
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("walls"); ap.add_argument("images", nargs="+"); ap.add_argument("--out", required=True)
    ap.add_argument("--no-markers", action="store_true"); ap.add_argument("--no-rings", action="store_true")
    ap.add_argument("--ring-dark", type=float, default=0.7)
    ap.add_argument("--ring-exclude", help="json {KEY: [[x0,y0,x1,y1],...]} boxes where ring centres are ignored (vines, art)")
    a_ = ap.parse_args()
    W = json.load(open(a_.walls))
    for spec in a_.images:
        key, _, rest = spec.partition("="); path, _, box = rest.partition(":")
        a = np.array(Image.open(path).convert("RGB")).astype(int)
        segs = W[key]
        if not a_.no_markers:
            found, zone = find_markers(a)
            H, Wd = zone.shape
            def inz(x, y): return zone[min(max(int(y), 0), H - 1), min(max(int(x), 0), Wd - 1)]
            before = len(segs)
            segs = [s for s in segs if s[4] != 1 or not inz((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)]
            # reconnect across each marker
            deg = degree(segs); add = []
            ends = [p for p, d in deg.items() if d == 1]
            for mx, my, rx, ry in found:
                near = [p for p in ends if abs(p[0] - mx) < rx + 80 and abs(p[1] - my) < ry + 80]
                used = set()
                for i, p in enumerate(near):
                    for q in near[i + 1:]:
                        if p in used or q in used: continue
                        horiz = abs(p[1] - q[1]) <= 12 and (p[0] - mx) * (q[0] - mx) < 0
                        vert = abs(p[0] - q[0]) <= 12 and (p[1] - my) * (q[1] - my) < 0
                        if horiz or vert:
                            add.append([p[0], p[1], q[0], q[1], 1]); used |= {p, q}
            segs = segs + add
            print(key, "markers", len(found), "removed", before - (len(segs) - len(add)), "reconnected", len(add))
        if not a_.no_rings:
            g = cv2.medianBlur(a.mean(-1).astype(np.uint8), 5)
            x0, y0, x1, y1 = map(int, box.split(",")) if box else (0, 0, g.shape[1], g.shape[0])
            small = cv2.resize(g[y0:y1, x0:x1], None, fx=0.5, fy=0.5)
            cs = cv2.HoughCircles(small, cv2.HOUGH_GRADIENT, dp=1, minDist=30, param1=80, param2=30,
                                  minRadius=50, maxRadius=210)
            if cs is not None:
                cs = cs * 2
            dark = g < 60
            dark = ndi.binary_dilation(dark, iterations=4)
            rings = []
            exb = (json.load(open(a_.ring_exclude)).get(key, []) if a_.ring_exclude else [])
            for cx, cy, r in (cs[0] if cs is not None else []):
                cx += x0; cy += y0
                t = np.linspace(0, 2 * np.pi, 360, endpoint=False)
                xs = np.clip((cx + r * np.cos(t)).astype(int), 0, g.shape[1] - 1); ys = np.clip((cy + r * np.sin(t)).astype(int), 0, g.shape[0] - 1)
                if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in exb): continue
                if dark[ys, xs].mean() >= a_.ring_dark:
                    if all(math.hypot(cx - c2[0], cy - c2[1]) > 15 or abs(r - c2[2]) > 15 for c2 in rings):
                        rings.append((cx, cy, r))
            wm = np.zeros(g.shape, np.uint8); om = np.zeros(g.shape, np.uint8)
            for s_ in segs:
                cv2.line(wm if s_[4] == 1 else om, (int(s_[0]), int(s_[1])), (int(s_[2]), int(s_[3])), 1, 1)
            dw = cv2.distanceTransform(1 - wm, cv2.DIST_L2, 5); do = cv2.distanceTransform(1 - om, cv2.DIST_L2, 5)
            add = []
            for cx, cy, r in rings:
                n = max(24, int(2 * math.pi * r / 25))
                for i in range(n):
                    a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
                    p = (cx + r * math.cos(a0), cy + r * math.sin(a0)); q = (cx + r * math.cos(a1), cy + r * math.sin(a1))
                    m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                    if not dark[int(m[1]), int(m[0])]: continue          # no drawn wall here (doorway / opening)
                    if dw[int(m[1]), int(m[0])] < 14 or do[int(m[1]), int(m[0])] < 25: continue
                    add.append([round(p[0]), round(p[1]), round(q[0]), round(q[1]), 1])
            segs = segs + add
            print(key, "rings", len(rings), [tuple(map(int, c)) for c in rings], "added", len(add))
        W[key] = segs
    json.dump(W, open(a_.out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
