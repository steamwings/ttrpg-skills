#!/usr/bin/env python3
"""Apply review fixes to an existing walls.json (the output of detect_walls.py / postprocess.py).

  apply_fixes.py walls.json fixes.json --out walls2.json [L1=floor1.webp L2=...]

Images are optional; they are needed for `drop_on_floor` and for arcs with `windows: true`.

fixes.json:
{
  "drop_zero": true,                 # zero-length segments (degenerate openings) -> gone
  "prune_spurs": 40,                 # kind-1 dead ends shorter than this (px) whose other end is a junction
  "drop_on_floor": {"min": 175, "frac": 0.5},   # kind-1 walls lying on open pale floor / clouds
  "snap": 15,                        # added wall ends snap to existing endpoints within this
  "L1": {
    "remove": [{"box": [x0,y0,x1,y1], "kinds": [1], "rule": "mid"}],   # rule mid|all (both ends inside)
    "add":    [[x0,y0,x1,y1,kind], ...],
    "arcs":   [{"c": [cx,cy], "r": R, "from": deg, "to": deg, "step": 6, "windows": true, "band": 15}],
    "cuts":   [{"line": [x0,y0,x1,y1], "width": 60}],  # open a passage along this axis (ramp/bridge mouths)
    "rebuild": [{"line": [x0,y0,x1,y1], "band": 30}], # one clean wall along a messy straight wall, openings kept
    "remove_annulus": [{"c": [cx,cy], "r": [r0,r1]}],  # clear a ring (e.g. junk on a ring staircase)
    "bays":    [{"c": [door centre], "n": [outward normal], "r": R}],  # balcony: edge arc (sees out), base tangle cleared
    "protect": [{"line": [...], "width": 60}]         # passages join_dead_ends must not close (cuts are protected too)
  },
  "dedupe_parallel": {"dist": 16, "angle": 12, "overlap": 0.7},  # walls alongside doors/windows/longer walls
  "collapse_loops": {"max_len": 90, "max_w": 35},   # tiny wall loops (around window slits) -> one window/wall
  "join_dead_ends": {"max_gap": 90}                 # close holes between facing dead ends
}
}
Angles are image-space degrees (y down): 270 = straight up. An arc goes from `from` to `to` increasing.
Order: drop_zero -> drop_on_floor -> remove -> cuts -> arcs/add -> bays -> collapse_loops -> rebuild -> dedupe_parallel -> join_dead_ends -> prune_spurs.
"""
import argparse, json, math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree


def inbox(x, y, b): return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def endpoints(segs):
    return [(s[0], s[1]) for s in segs] + [(s[2], s[3]) for s in segs]


def snap_pt(p, pts, r):
    if not pts or r <= 0: return p
    d, i = cKDTree(pts).query(p)
    return tuple(pts[i]) if d <= r else p


def arc_segments(a, arc):
    cx, cy = arc["c"]; R = arc["r"]; t0, t1 = arc["from"], arc["to"]
    step_px = arc.get("step", 6) * 4  # target chord length ~24px
    n = max(2, int(math.radians(t1 - t0) * R / step_px) + 1)
    ts = np.linspace(math.radians(t0), math.radians(t1), n + 1)
    pts = [(cx + R * math.cos(t), cy + R * math.sin(t)) for t in ts]
    kinds = [1] * n
    if arc.get("windows") and a is not None:
        band = arc.get("band", 15); H, W = a.shape[:2]
        for i in range(n):
            tm = (ts[i] + ts[i + 1]) / 2
            rr = np.arange(R - band, R + band + 1)
            xs = np.clip((cx + rr * math.cos(tm)).astype(int), 0, W - 1); ys = np.clip((cy + rr * math.sin(tm)).astype(int), 0, H - 1)
            if (a[ys, xs].min(-1) > 235).mean() > 0.3: kinds[i] = 3
    return [[round(pts[i][0]), round(pts[i][1]), round(pts[i + 1][0]), round(pts[i + 1][1]), kinds[i]] for i in range(n)]


def prune(segs, L):
    for _ in range(3):
        pts = np.array(endpoints(segs), float)
        if not len(pts): return segs
        tree = cKDTree(pts)
        deg = np.array([len(tree.query_ball_point(p, 4)) for p in pts])
        n = len(segs); keep = []
        for i, s in enumerate(segs):
            ln = math.hypot(s[2] - s[0], s[3] - s[1])
            d0, d1 = deg[i], deg[i + n]
            spur = s[4] == 1 and ln < L and ((d0 == 1 and d1 >= 3) or (d1 == 1 and d0 >= 3) or (d0 == 1 and d1 == 1 and ln < L / 2))
            if not spur: keep.append(s)
        if len(keep) == len(segs): break
        segs = keep
    return segs


def seg_intersect(p1, p2, p3, p4):
    def cr(a, b, c): return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = cr(p3, p4, p1), cr(p3, p4, p2), cr(p1, p2, p3), cr(p1, p2, p4)
    return d1 * d2 <= 0 and d3 * d4 <= 0


def cut(segs, line, width, kinds=(1, 3)):
    """Open a passage: remove the part of every wall crossing `line` (the passage axis) that lies within width/2."""
    A = np.array(line[:2], float); B = np.array(line[2:4], float); u = (B - A) / np.linalg.norm(B - A); nrm = np.array([-u[1], u[0]])
    h = width / 2; out = []
    for s in segs:
        P0 = np.array(s[:2], float); P1 = np.array(s[2:4], float)
        if s[4] not in kinds: out.append(s); continue
        d0, d1 = (P0 - A) @ nrm, (P1 - A) @ nrm
        if abs(d1 - d0) < 1e-6:                                # parallel to the axis: a side rail, keep
            out.append(s); continue
        ta, tb = sorted(((-h - d0) / (d1 - d0), (h - d0) / (d1 - d0)))
        lo, hi = max(ta, 0.0), min(tb, 1.0)
        mid = P0 + (P1 - P0) * (lo + hi) / 2; along = (mid - A) @ u
        # only walls that actually cross the passage band, within the axis' length
        if hi <= lo or not (0 <= along <= np.linalg.norm(B - A)) or abs(u @ ((P1 - P0) / np.linalg.norm(P1 - P0))) > 0.9:
            out.append(s); continue
        for t0, t1 in ((0.0, ta), (tb, 1.0)):
            t0, t1 = max(t0, 0.0), min(t1, 1.0)
            if t1 - t0 > 0 and np.linalg.norm(P1 - P0) * (t1 - t0) > 3:
                q0 = P0 + (P1 - P0) * t0; q1 = P0 + (P1 - P0) * t1
                out.append([round(q0[0]), round(q0[1]), round(q1[0]), round(q1[1]), s[4]])
    return out


def dedupe_parallel(segs, dist=16, angle=12, overlap=0.7):
    """Drop a kind-1 wall that runs alongside a door/window or a longer wall (double lines, walls over doors)."""
    S = np.array([s[:4] for s in segs], float); K = np.array([s[4] for s in segs])
    D = S[:, 2:4] - S[:, 0:2]; L = np.hypot(D[:, 0], D[:, 1]) + 1e-9; U = D / L[:, None]
    alive = np.ones(len(segs), bool); ca = math.cos(math.radians(angle))
    for i in np.argsort(L):
        if K[i] != 1 or L[i] < 4: continue
        cand = alive.copy(); cand[i] = False
        cand &= (K == 2) | (K == 3) | ((K == 1) & (L >= L[i]))
        cand &= np.abs(U @ U[i]) > ca
        if not cand.any(): continue
        idx = np.nonzero(cand)[0]
        A = S[idx, 0:2]; u = U[idx]; nrm = np.stack([-u[:, 1], u[:, 0]], 1)
        P0 = S[i, 0:2]; P1 = S[i, 2:4]
        e0 = ((P0 - A) * nrm).sum(1); e1 = ((P1 - A) * nrm).sum(1)
        t0 = ((P0 - A) * u).sum(1); t1 = ((P1 - A) * u).sum(1)
        lo, hi = np.minimum(t0, t1), np.maximum(t0, t1)
        ov = (np.minimum(hi, L[idx]) - np.maximum(lo, 0)).clip(0) / (hi - lo + 1e-9)
        if ((np.abs(e0) <= dist) & (np.abs(e1) <= dist) & (ov >= overlap)).any(): alive[i] = False
    return [s for s, a in zip(segs, alive) if a]


def rebuild_line(segs, rb):
    """Replace a messy straight wall (double lines, X crossings) by one clean wall along `line`, keeping the
    openings that sit on it and re-attaching walls that dead-end against it."""
    A = np.array(rb["line"][:2], float); B = np.array(rb["line"][2:4], float); Ln = np.linalg.norm(B - A)
    u = (B - A) / Ln; nrm = np.array([-u[1], u[0]]); band = rb.get("band", 30)
    def rel(p): q = np.array(p, float) - A; return q @ u, q @ nrm
    keep, opens = [], []
    for s in segs:
        al, d = rel(((s[0] + s[2]) / 2, (s[1] + s[3]) / 2))
        on = abs(d) < band and -band <= al <= Ln + band
        if not on: keep.append(s); continue
        if s[4] == 1: continue
        ln = math.hypot(s[2] - s[0], s[3] - s[1])
        if s[4] in (2, 3) and abs(d) <= rb.get("opening_offset", 12) and ln <= rb.get("max_opening", 80):
            a0, a1 = rel(s[:2])[0], rel(s[2:4])[0]
            p0, p1 = (s[:2], s[2:4]) if a0 <= a1 else (s[2:4], s[:2])
            opens.append((min(a0, a1), p0, p1, s)); keep.append(s)
        elif s[4] == 4: keep.append(s)
    opens.sort(key=lambda o: o[0]); cur = [round(A[0]), round(A[1])]; new = []
    for _, p0, p1, _s in opens:
        new.append([cur[0], cur[1], int(p0[0]), int(p0[1]), 1]); cur = [int(p1[0]), int(p1[1])]
    new.append([cur[0], cur[1], round(B[0]), round(B[1]), 1])
    new = [w for w in new if math.hypot(w[2] - w[0], w[3] - w[1]) > 1]
    # re-attach dead ends that stop short of the rebuilt wall
    pts = np.array(endpoints(keep), float); tree = cKDTree(pts) if len(pts) else None
    for s in keep:
        if s[4] != 1: continue
        for p in (s[:2], s[2:4]):
            al, d = rel(p)
            if 1.5 < abs(d) < rb.get("attach", 22) and 0 <= al <= Ln and len(tree.query_ball_point(p, 4)) == 1:
                q = A + u * al; new.append([int(p[0]), int(p[1]), round(q[0]), round(q[1]), 1])
    return keep + new


def _nodes(segs, tol=4):
    pts = np.array(endpoints(segs), float); n = len(segs)
    if not len(pts): return pts, np.zeros(0, int)
    tree = cKDTree(pts); lab = -np.ones(len(pts), int); c = 0
    for i in range(len(pts)):
        if lab[i] >= 0: continue
        for j in tree.query_ball_point(pts[i], tol):
            if lab[j] < 0: lab[j] = c
        c += 1
    return pts, lab


def collapse_loops(segs, a, max_len=90, max_w=35, white=0.12):
    """Small closed loops of walls (drawn around a white window slit, or junk triangles) -> one segment along the
    loop's long axis: a window if the loop encloses white slit pixels, else a wall. Re-attach the loop's exits."""
    import networkx as nx, cv2
    pts, lab = _nodes(segs); n = len(segs); G = nx.Graph()
    for i, s in enumerate(segs):
        if s[4] == 1 and lab[i] != lab[i + n]: G.add_edge(lab[i], lab[i + n], i=i)
    pos = {}
    for i in range(len(pts)): pos.setdefault(lab[i], pts[i])
    drop, add, used = set(), [], set()
    for cy in nx.cycle_basis(G):
        if len(cy) > 8 or used & set(cy): continue
        P = np.array([pos[v] for v in cy], np.float32)
        (cx, cy_), (rw, rh), ang = cv2.minAreaRect(P)
        if max(rw, rh) > max_len or min(rw, rh) > max_w: continue
        used |= set(cy)
        L = max(rw, rh); t = math.radians(ang if rw >= rh else ang + 90); u = np.array([math.cos(t), math.sin(t)])
        e0 = np.array([cx, cy_]) - u * L / 2; e1 = np.array([cx, cy_]) + u * L / 2
        kind = 1
        if a is not None:
            mask = np.zeros(a.shape[:2], np.uint8); cv2.fillPoly(mask, [P.astype(np.int32)], 1)
            if mask.sum() and (a[mask.astype(bool)].min(-1) > 235).mean() > white: kind = 3
        cyc_edges = {G[cy[j]][cy[(j + 1) % len(cy)]]["i"] for j in range(len(cy))}
        drop |= cyc_edges
        add.append([round(e0[0]), round(e0[1]), round(e1[0]), round(e1[1]), kind])
        for v in cy:   # exits: other edges leaving the loop -> join their node to the nearer end
            if any(G[v][w]["i"] not in cyc_edges for w in G[v]):
                p = pos[v]; e = e0 if np.linalg.norm(p - e0) <= np.linalg.norm(p - e1) else e1
                if np.linalg.norm(p - e) > 2: add.append([round(p[0]), round(p[1]), round(e[0]), round(e[1]), 1])
    return [s for i, s in enumerate(segs) if i not in drop] + add


def join_dead_ends(segs, a, max_gap=90, protect=(), floor=175):
    """Join mutually-nearest dead ends (kind-1 endpoints with nothing attached) when the join crosses no wall,
    doesn't run over open pale floor, and isn't inside a protected passage (ramp cuts)."""
    pts, lab = _nodes(segs); n = len(segs)
    cnt = np.bincount(lab)
    dead = [i for i in range(len(pts)) if cnt[lab[i]] == 1 and segs[i % n][4] == 1]
    if len(dead) < 2: return segs
    D = pts[dead]; tree = cKDTree(D)
    bright = ndi.minimum_filter(a.min(-1), size=9) > floor if a is not None else None
    def protected(p):
        for c in protect:
            A = np.array(c["line"][:2], float); B = np.array(c["line"][2:4], float); u = (B - A) / np.linalg.norm(B - A)
            q = p - A
            if abs(q @ np.array([-u[1], u[0]])) < c.get("width", 60) / 2 + 20 and -20 <= q @ u <= np.linalg.norm(B - A) + 20: return True
        return False
    out = list(segs); done = set()
    for j, p in enumerate(D):
        if j in done or protected(p): continue
        d, k = tree.query(p, k=2); k = k[1]; d = d[1]
        if d > max_gap or k in done or protected(D[k]): continue
        if tree.query(D[k], k=2)[1][1] != j: continue          # mutual nearest only
        q = D[k]
        if any(seg_intersect(p, q, np.array(s[:2], float), np.array(s[2:4], float)) for s in segs
               if min(np.linalg.norm(np.array(s[:2]) - p), np.linalg.norm(np.array(s[2:4]) - p),
                      np.linalg.norm(np.array(s[:2]) - q), np.linalg.norm(np.array(s[2:4]) - q)) > 3): continue
        if bright is not None:
            m = int(d / 3) + 2; H, Wd = bright.shape
            xs = np.clip(np.linspace(p[0], q[0], m).astype(int), 0, Wd - 1); ys = np.clip(np.linspace(p[1], q[1], m).astype(int), 0, H - 1)
            if bright[ys, xs].mean() > 0.4: continue
        out.append([int(p[0]), int(p[1]), int(q[0]), int(q[1]), 1]); done |= {j, k}
    return out


def bay(segs, b):
    """Balcony / bay: half-disk outside a door. Its parapet becomes an edge arc (kind 4: blocks movement, not sight),
    the tangle at its base is cleared, and walls inside the half-disk are dropped."""
    c = np.array(b["c"], float); nv = np.array(b["n"], float); nv /= np.linalg.norm(nv); t = np.array([-nv[1], nv[0]]); R = b["r"]
    out = []
    for s in segs:
        if s[4] != 1: out.append(s); continue
        P0 = np.array(s[:2], float); P1 = np.array(s[2:4], float); m = (P0 + P1) / 2 - c; d = m @ nv
        v = P1 - P0; ln = np.linalg.norm(v) or 1
        if d > 5 and np.linalg.norm(m) < R + 30: continue
        if -25 < d <= 5 and abs(m @ t) < R + 25 and abs(v @ t) / ln < 0.9: continue
        out.append(s)
    ext = math.radians(b.get("extend", 8)); n_ = 12
    ths = np.linspace(-ext, math.pi + ext, n_ + 1)
    P = [c + R * (math.cos(x) * t + math.sin(x) * nv) for x in ths]
    out += [[round(P[i][0]), round(P[i][1]), round(P[i + 1][0]), round(P[i + 1][1]), b.get("kind", 4)] for i in range(n_)]
    # close the base: arc ends -> the door's ends (the door sits on the base line at c)
    doors = [s for s in out if s[4] == 2 and np.linalg.norm((np.array(s[:2]) + np.array(s[2:4])) / 2 - c) < 25]
    if doors:
        dpts = [np.array(doors[0][:2], float), np.array(doors[0][2:4], float)]
        for e in (P[0], P[-1]):
            q = min(dpts, key=lambda p: np.linalg.norm(p - e))
            out.append([round(e[0]), round(e[1]), int(q[0]), int(q[1]), 1])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("walls"); ap.add_argument("fixes"); ap.add_argument("images", nargs="*")
    ap.add_argument("--out", required=True); o = ap.parse_intermixed_args()
    W = json.load(open(o.walls)); F = json.load(open(o.fixes))
    imgs = {k: v for k, _, v in (s.partition("=") for s in o.images)}
    for key in W:
        segs = [list(s[:5]) for s in W[key]]; n0 = len(segs); fx = F.get(key, {})
        a = np.array(Image.open(imgs[key]).convert("RGB")).astype(int) if key in imgs else None
        if F.get("drop_zero", True):
            segs = [s for s in segs if (s[0], s[1]) != (s[2], s[3])]
        fl = F.get("drop_on_floor")
        if fl and a is not None:
            bright = ndi.minimum_filter(a.min(-1), size=9) > fl.get("min", 175); H, Wd = bright.shape; keep = []
            for s in segs:
                ln = math.hypot(s[2] - s[0], s[3] - s[1])
                if s[4] == 1 and ln >= 12:
                    m = int(ln / 3) + 2
                    xs = np.clip(np.linspace(s[0], s[2], m).astype(int), 0, Wd - 1); ys = np.clip(np.linspace(s[1], s[3], m).astype(int), 0, H - 1)
                    if bright[ys, xs].mean() > fl.get("frac", 0.5): continue
                keep.append(s)
            segs = keep
        for r in fx.get("remove", []):
            kinds = r.get("kinds", [1]); b = r["box"]; rule = r.get("rule", "mid")
            def hit(s):
                if s[4] not in kinds: return False
                if rule == "all": return inbox(s[0], s[1], b) and inbox(s[2], s[3], b)
                return inbox((s[0] + s[2]) / 2, (s[1] + s[3]) / 2, b)
            segs = [s for s in segs if not hit(s)]
        for an in fx.get("remove_annulus", []):   # {"c":[x,y],"r":[r0,r1],"kinds":[1]}
            cx_, cy_ = an["c"]; r0, r1 = an["r"]; ks = an.get("kinds", [1])
            segs = [s_ for s_ in segs if not (s_[4] in ks and r0 <= math.hypot((s_[0] + s_[2]) / 2 - cx_, (s_[1] + s_[3]) / 2 - cy_) <= r1)]
        for c in fx.get("cuts", []):
            segs = cut(segs, c["line"], c.get("width", 60), tuple(c.get("kinds", [1, 3])))
        pts = endpoints(segs); sn = F.get("snap", 15)
        new = [list(x) for x in fx.get("add", [])]
        for arc in fx.get("arcs", []):
            arcsegs = arc_segments(a, arc)
            # snap only the two outer ends of the arc
            arcsegs[0][0:2] = snap_pt(tuple(arcsegs[0][0:2]), pts, arc.get("snap", 30))
            arcsegs[-1][2:4] = snap_pt(tuple(arcsegs[-1][2:4]), pts, arc.get("snap", 30))
            segs += arcsegs
        for s in new:
            p0 = snap_pt((s[0], s[1]), pts, sn); p1 = snap_pt((s[2], s[3]), pts, sn)
            segs.append([int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]), s[4] if len(s) > 4 else 1])
        for b in fx.get("bays", []):
            segs = bay(segs, b)
        if F.get("collapse_loops"):
            nb = len(segs); segs = collapse_loops(segs, a, **F["collapse_loops"]); print(f"  {key}: collapse_loops {nb} -> {len(segs)}")
        for rb in fx.get("rebuild", []):
            segs = rebuild_line(segs, rb)
        if F.get("dedupe_parallel"):
            dp = F["dedupe_parallel"]; nb = len(segs)
            segs = dedupe_parallel(segs, dp.get("dist", 16), dp.get("angle", 12), dp.get("overlap", 0.7))
            print(f"  {key}: dedupe_parallel removed {nb - len(segs)}")
        if F.get("join_dead_ends"):
            nb = len(segs); jd = F["join_dead_ends"]
            segs = join_dead_ends(segs, a, jd.get("max_gap", 90), fx.get("cuts", []) + fx.get("protect", []), jd.get("floor", 175))
            print(f"  {key}: join_dead_ends added {len(segs) - nb}")
        if F.get("prune_spurs"):
            segs = prune(segs, F["prune_spurs"])
        W[key] = segs
        print(f"{key}: {n0} -> {len(segs)}")
    json.dump(W, open(o.out, "w"))


if __name__ == "__main__":
    main()
