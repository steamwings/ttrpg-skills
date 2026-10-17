#!/usr/bin/env python3
"""Add walls that sit ON GRID LINES and are drawn only as thin black outlines (Palace of Heart's Desire interior
walls: black line / pale core / black line, ~15px, too thin and too pale for colour masks).

  grid_walls.py walls.json --out walls-plus.json L1=floor1.webp L2=floor2.webp [--grid 100] [--frac 0.85]

For every 1-square grid edge, look across it (±win px) at each point along it: the point counts if there is a
short dark run there (1..max_run px with brightness < dark). Edge = wall when >= frac of its points count.
Solid dark areas (dark floors, rugs) have runs longer than max_run and don't count. Edges already covered by an
existing wall (parallel within 20px), or crossing a door/window, are skipped. New walls are merged into
straight runs and added as kind 1.
"""
import argparse, json
import numpy as np
from PIL import Image


def edge_ok(prof, dark, max_run, min_run=3):
    """True if the profile across the edge has a dark run of min_run..max_run px. The drawn GRID is a 1-2px
    black line, so min_run 3 rejects it; solid dark floors/rugs give runs longer than max_run."""
    d = np.concatenate([[False], prof < dark, [False]]).astype(int)
    starts = np.where(np.diff(d) == 1)[0]; ends = np.where(np.diff(d) == -1)[0]
    runs = ends - starts
    if not len(runs) or runs.max() > max_run or d.sum() > max_run:
        return False
    return (runs >= min_run).any()


def covered(seg, segs, tol=20):
    x0, y0, x1, y1 = seg
    for s in segs:
        a0, b0, a1, b1 = s[:4]
        if y0 == y1 and abs(b1 - b0) <= abs(a1 - a0) * 0.2:          # horizontal
            if abs((b0 + b1) / 2 - y0) <= tol and min(a0, a1) <= (x0 + x1) / 2 <= max(a0, a1):
                return True
        if x0 == x1 and abs(a1 - a0) <= abs(b1 - b0) * 0.2:          # vertical
            if abs((a0 + a1) / 2 - x0) <= tol and min(b0, b1) <= (y0 + y1) / 2 <= max(b0, b1):
                return True
    return False


def covered_point(p, segs, tol=20):
    for s in segs:
        A = np.array(s[:2], float); B = np.array(s[2:4], float); P = np.array(p, float); AB = B - A; L2 = AB @ AB
        u = 0 if L2 == 0 else np.clip((P - A) @ AB / L2, 0, 1)
        if np.linalg.norm(A + u * AB - P) <= tol:
            return True
    return False


def near_opening(seg, segs, tol=25):
    x0, y0, x1, y1 = seg; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for s in segs:
        if s[4] in (2, 3):
            mx, my = (s[0] + s[2]) / 2, (s[1] + s[3]) / 2
            L = max(abs(s[2] - s[0]), abs(s[3] - s[1])) / 2 + tol
            if abs(mx - cx) <= L + 50 and abs(my - cy) <= L + 50 and (abs(mx - cx) < tol or abs(my - cy) < tol):
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("walls"); ap.add_argument("images", nargs="+"); ap.add_argument("--out", required=True)
    ap.add_argument("--grid", type=int, default=100); ap.add_argument("--frac", type=float, default=0.85)
    ap.add_argument("--win", type=int, default=14); ap.add_argument("--dark", type=int, default=40)
    ap.add_argument("--max-run", type=int, default=16)
    ap.add_argument("--exclude", help='json {"KEY": [[x,y,x,y,...] polygon, ...]} areas with no grid walls (stairs, voids)')
    a_ = ap.parse_args()
    W = json.load(open(a_.walls)); g = a_.grid
    ex = json.load(open(a_.exclude)) if a_.exclude else {}
    for spec in a_.images:
        key, _, path = spec.partition("=")
        a = np.array(Image.open(path).convert("RGBA")).astype(int)
        br = a[..., :3].mean(-1); br[a[..., 3] == 0] = 255
        H, Wd = br.shape; segs = W.get(key, []); new = []
        for gy in range(g, H - g + 1, g):                 # horizontal edges
            for gx in range(0, Wd - g, g):
                pts = [edge_ok(br[gy - a_.win:gy + a_.win, x], a_.dark, a_.max_run) for x in range(gx + 5, gx + g - 5, 3)]
                if np.mean(pts) >= a_.frac:
                    new.append([gx, gy, gx + g, gy])
        for gx in range(g, Wd - g + 1, g):                # vertical edges
            for gy in range(0, H - g, g):
                pts = [edge_ok(br[y, gx - a_.win:gx + a_.win], a_.dark, a_.max_run) for y in range(gy + 5, gy + g - 5, 3)]
                if np.mean(pts) >= a_.frac:
                    new.append([gx, gy, gx, gy + g])
        new = [s for s in new if not covered(s, segs) and not near_opening(s, segs)]
        if ex.get(key):
            import cv2
            polys = [np.array(p, np.float32).reshape(-1, 2) for p in ex[key]]
            new = [s for s in new if all(cv2.pointPolygonTest(p, ((s[0] + s[2]) / 2, (s[1] + s[3]) / 2), False) < 0 for p in polys)]
        # merge consecutive unit edges into runs
        hs = sorted([s for s in new if s[1] == s[3]], key=lambda s: (s[1], s[0]))
        vs = sorted([s for s in new if s[0] == s[2]], key=lambda s: (s[0], s[1]))
        merged = []
        for group, axis in ((hs, 0), (vs, 1)):
            cur = None
            for s in group:
                if cur and ((axis == 0 and s[1] == cur[1] and s[0] == cur[2]) or (axis == 1 and s[0] == cur[0] and s[1] == cur[3])):
                    cur[2], cur[3] = s[2], s[3]
                else:
                    if cur: merged.append(cur + [1])
                    cur = list(s)
            if cur: merged.append(cur + [1])
        # isolated single-square pieces are usually furniture edges: keep a run only if it spans >= 2 squares
        # or one of its ends touches an existing wall/door
        ends = np.array([p for s in segs for p in ((s[0], s[1]), (s[2], s[3]))], float) if segs else np.zeros((0, 2))
        def touches(p):
            if not len(ends): return False
            if np.min(np.hypot(ends[:, 0] - p[0], ends[:, 1] - p[1])) <= 35: return True
            return covered_point(p, segs)
        merged = [m for m in merged if max(abs(m[2] - m[0]), abs(m[3] - m[1])) >= 2 * g or touches(m[:2]) or touches(m[2:4])]
        W[key] = segs + merged
        print(key, "unit edges", len(new), "-> added runs", len(merged))
    json.dump(W, open(a_.out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
