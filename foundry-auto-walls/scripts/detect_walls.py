#!/usr/bin/env python3
"""Detect walls, doors and windows in a battle-map image and vectorise them for Foundry VTT.

Usage
-----
  # detect (one image per level; KEY is any label you will map to a Level name later)
  detect_walls.py --out walls.json L1=floor1.webp L2=floor2.webp L3=floor3.webp

  # with a non-default colour profile and reproducible manual fixes
  detect_walls.py --profile profiles.json:witchlight --fixes fixes.json --out walls.json L1=...

  # calibrate colours for a new map style: print mean RGB around points
  detect_walls.py --sample 200,400 --sample 350,598 --sample 345,95 L2=floor2.webp

Output
------
walls.json : {"L1": [[x0, y0, x1, y1, kind], ...], ...}
             kind 1 = wall, 2 = door, 3 = window, 4 = edge (sky/cliff border: blocks movement only).  Coordinates are IMAGE pixels —
             push_walls.js adds scene.dimensions.sceneX/sceneY (the scene padding offset).
overlay-<KEY>.png (next to --out) : red walls, blue doors, cyan windows, for visual review.
ALWAYS look at the overlays before pushing.

fixes.json (optional) : {"L2": {"remove_boxes": [[x0,y0,x1,y1], ...],
                               "add": [[x0,y0,x1,y1,kind], ...]}}
  remove_boxes drops every detected segment lying fully inside the box (junk blobs);
  add appends hand-placed segments (missed windows, exterior stair boxes, image-edge walls).
  Door/window endpoints are snapped to nearby wall endpoints AFTER fixes are applied.

Pipeline (see SKILL.md for the reasoning)
-----------------------------------------
colour masks -> close(5) THEN open(7) -> drop blobs (distance-transform thickness)
-> door rectangles (white, rect-fill test) -> bridge collinear gaps (1-D closing)
-> gaps containing glass colour = windows -> skeletonize union -> prune spurs
-> trace paths (skan) -> split by class -> Douglas-Peucker -> axis snap
-> cluster endpoints -> drop tiny isolated wall clusters -> fixes -> snap doors.
"""
import argparse, json, os, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize
from skimage.measure import approximate_polygon

try:
    from skan import Skeleton, summarize
except ImportError:
    sys.exit("pip install skan --break-system-packages")

# Tuned on the Wild Beyond the Witchlight book maps (grey-beige stone walls with black
# outlines, pure-white door rectangles, pale-green glass strips in exterior walls).
DEFAULT_PROFILE = {
    "wall":  {"br": [120, 215], "rg_abs": 16, "rb": [18, 60], "gr_max": 12},
    "door":  {"min_rgb": [235, 235, 228]},
    "glass": {"gr_min": 22, "rb_min": 5, "br": [85, 165]},
    "close": 5,            # px, heals texture cracks in the wall mask (run BEFORE opening)
    "open": 7,             # px, kills grid lines / furniture outlines (walls here are ~16px)
    "wall_max_half_thickness": 13,   # blobs thicker than this (rugs, pools of colour) are dropped
    "min_wall_area": 1500,
    "door_len": [35, 130], "door_thick": [10, 30], "door_fill": 0.75,
    "bridge": 61,          # max gap (px) bridged along a wall to look for windows
    "min_glass_px": 20,
    "spur": 14,            # prune skeleton spurs shorter than this
    "simplify": 2.5,       # Douglas-Peucker tolerance (px)
    "axis_snap": 0.07,     # |dy|/|dx| below this -> perfectly horizontal (and vice versa)
    "endpoint_merge": 7,   # px
    "min_cluster": 150,    # px of total length; smaller isolated wall clusters are junk
    "door_snap": 25,       # px; door/window ends jump to the nearest wall endpoint
}


def load_profile(spec):
    prof = dict(DEFAULT_PROFILE)
    if spec:
        path, _, name = spec.partition(":")
        data = json.load(open(path))
        prof.update(data[name] if name else data)
    return prof


def colour_masks(a, P):
    R, G, B, A = (a[..., i].astype(int) for i in range(4))
    br = (R + G + B) / 3
    w = P["wall"]
    wall = ((A > 0) & (br > w["br"][0]) & (br < w["br"][1]) & (np.abs(R - G) < w["rg_abs"])
            & (R - B > w["rb"][0]) & (R - B < w["rb"][1]) & (G - R < w["gr_max"]))
    d = P["door"]["min_rgb"]
    door = (A > 0) & (R > d[0]) & (G > d[1]) & (B > d[2])
    g = P["glass"]
    glass = (A > 0) & (G - R > g["gr_min"]) & (R - B > g["rb_min"]) & (br > g["br"][0]) & (br < g["br"][1])
    return wall, door, glass


def clean_walls(wall, P):
    if P.get("mask") == "outline":
        # Thick black outline walls (Motherhorn). A DISK opening of radius ~3 keeps bands >= 7px and
        # removes everything thin: rock cracks, the outlines of rivets/studs/furniture along the walls,
        # grid lines. The survivors that are not walls are small dots; drop components whose
        # bounding box is shorter than min_blob_extent.
        r = P.get("open_disk", 3)
        disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        w = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_OPEN, disk)
        n, lab, st, _ = cv2.connectedComponentsWithStats(w, connectivity=8)
        keep = np.zeros(n, bool)
        keep[1:] = np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) >= P.get("min_blob_extent", 60)
        return keep[lab]
    wall = ndi.binary_closing(wall, np.ones((P["close"],) * 2))
    wall = ndi.binary_opening(wall, np.ones((P["open"],) * 2))
    dt = ndi.distance_transform_edt(wall)
    if P.get("thick_mode") == "erase":
        # Erase only the thick blobs (shadows, black rock mottling touching the walls) and keep the
        # thin lines around them. "drop" (default) removes a whole component when any part of it is
        # thick, which loses entire room outlines when one wall touches a dark blob (Motherhorn).
        h = P["wall_max_half_thickness"]
        wall = wall & ~ndi.binary_dilation(dt > h, iterations=int(h) + 2)
        wall = ndi.binary_opening(wall, np.ones((3, 3)))
        lab, k = ndi.label(wall)
        sz = ndi.sum(wall, lab, range(1, k + 1))
        keep = np.zeros(k + 1, bool); keep[1:] = sz >= P["min_wall_area"]
        return keep[lab]
    lab, k = ndi.label(wall)
    keep = np.zeros(k + 1, bool)
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        comp = lab[sl] == j
        if comp.sum() >= P["min_wall_area"] and dt[sl][comp].max() <= P["wall_max_half_thickness"]:
            keep[j] = True
    return keep[lab]


def clean_doors(door, P):
    door = ndi.binary_opening(door, np.ones((P["open"],) * 2))
    g = P.get("door_merge_gap", 0)
    if g:
        # Double doors: two white leaves split by a thin black line. Close the gap along each axis so
        # both leaves become ONE door (one Foundry door opens the whole doorway).
        door = ndi.binary_closing(door, np.ones((1, g))) | ndi.binary_closing(door, np.ones((g, 1)))
    lab, _ = ndi.label(door)
    out = np.zeros_like(door)
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        comp = lab[sl] == j
        L, S = max(h, w), min(h, w)
        if (comp.sum() / (h * w) > P["door_fill"] and P["door_len"][0] <= L <= P["door_len"][1]
                and P["door_thick"][0] <= S <= P["door_thick"][1]):
            out[sl] |= comp
    return out


def dark_bands(a, cfg, extra=None):
    """Walls drawn as BLACK bands (thin interior walls on the Palace: black-tan-black, ~20px). Dark, unsaturated
    pixels -> close -> DISK opening (keeps bands >= 2r+1 px, drops grid lines and furniture outlines) ->
    erase blobs thicker than erase_half (map-key silhouettes, dark objects) -> drop small components."""
    R, G, B = (a[..., i].astype(int) for i in range(3))
    A = a[..., 3] if a.shape[2] > 3 else np.full(R.shape, 255)
    br = (R + G + B) / 3
    sat = np.max(a[..., :3], -1).astype(int) - np.min(a[..., :3], -1)
    m = ((A > 0) & (br < cfg.get("br", 45)) & (sat < cfg.get("sat", 30)))
    if extra is not None:
        m = m | extra            # e.g. the stone-colour mask: black outline + stone core = one wall band
    m = m.astype(np.uint8)
    # close merges the DOUBLE outline (black line, pale core, black line) into one band; a single thin line
    # (grid, furniture, marker rims) stays thin and is removed by the opening
    c = cfg.get("close", 5)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (c, c)))
    r = cfg.get("open_disk", 4)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    h = cfg.get("erase_half", 13)
    blob = cv2.dilate((dt > h).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4 * h + 1, 4 * h + 1)))
    m = m & (1 - blob)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) >= cfg.get("min_extent", 80)
    return keep[lab]


def sandwich_walls(a, cfg):
    """Walls drawn as a pale core between TWO black lines (Palace interior walls, ~15-20px). A pixel is wall core
    if a dark run of >= min_run px lies within `reach` px on both sides of it (above AND below, or left AND
    right). The 1px drawn grid never qualifies. Returns core | the black lines that bound it."""
    from scipy.ndimage import maximum_filter1d, binary_erosion
    br = a[..., :3].astype(int).mean(-1)
    if a.shape[2] > 3:
        br[a[..., 3] == 0] = 255
    dark = br < cfg.get("dark", 40)
    k = cfg.get("min_run", 3); R = cfg.get("reach", 14)
    out = np.zeros_like(dark)
    for axis in (0, 1):
        thick = binary_erosion(dark, structure=np.ones((k, 1) if axis == 0 else (1, k)))
        thick = ndi.binary_dilation(thick, structure=np.ones((k, 1) if axis == 0 else (1, k)))
        t = thick.astype(np.uint8)
        # before: any thick-dark in [p-R, p-1]; after: any in [p+1, p+R]
        W = 2 * (R // 2) + 1                     # odd window, centred
        m = maximum_filter1d(t, W, axis=axis, mode="constant")
        sh = W // 2 + 1
        before = np.zeros_like(m); after = np.zeros_like(m)
        if axis == 0:
            before[sh:] = m[:-sh]; after[:-sh] = m[sh:]
        else:
            before[:, sh:] = m[:, :-sh]; after[:, :-sh] = m[:, sh:]
        core = (before > 0) & (after > 0) & ~dark
        out |= core
    band = ndi.binary_closing(out, np.ones((5, 5)))
    band = band | (ndi.binary_dilation(band, iterations=6) & dark)
    h = cfg.get("erase_half")
    if h:   # thick filled blobs (spiral stair drawings, markers) are not walls
        dt = ndi.distance_transform_edt(band)
        band = band & ~ndi.binary_dilation(dt > h, iterations=int(h))
    if cfg.get("box"):          # only inside the building footprint (gardens, vines, frame art are not walls)
        x0, y0, x1, y1 = cfg["box"]; clip = np.zeros_like(band); clip[y0:y1, x0:x1] = True; band &= clip
    n, lab, st, _ = cv2.connectedComponentsWithStats(band.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) >= cfg.get("min_extent", 100)
    return keep[lab]


def white_blob_zone(door_raw, min_dim):
    """Map-key markers (white ovals with black silhouettes, callout triangles): white blobs whose BOTH sides
    exceed min_dim px. Returns a dilated zone where walls are suppressed."""
    m = ndi.binary_opening(door_raw, np.ones((5, 5)))
    lab, _ = ndi.label(m)
    z = np.zeros_like(m)
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if h > min_dim and w > min_dim and h < 400 and w < 400:
            z[sl] |= lab[sl] == j
    return ndi.binary_dilation(z, iterations=14)


def white_windows(door_raw, wall, P):
    """Windows drawn as small WHITE slits set into the wall band (Palace of Heart's Desire): white blobs
    shorter than a door (white_windows = [min_len, max_len]) that touch the wall mask on both sides."""
    lo, hi = P["white_windows"]
    m = ndi.binary_opening(door_raw, np.ones((3, 3)))
    lab, _ = ndi.label(m)
    near = ndi.binary_dilation(wall, iterations=10)   # slits sit inside a black outline, ~6-8px from the stone
    out = np.zeros_like(m)
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        comp = lab[sl] == j
        n = int(comp.sum())
        if n < 40 or n > 3000:
            continue
        ys, xs = np.nonzero(comp)
        (_, _), (rw, rh), _ = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))   # rotated slits too
        L, T = max(rw, rh), min(rw, rh)
        if lo <= L < hi and 4 <= T <= 16 and n / max(L * T, 1) > 0.6 and (near[sl] & comp).sum() > 0.5 * n:
            out[sl] |= comp
    return out


def find_windows(solid, glass, P):
    K = P["bridge"]
    bridged = np.zeros_like(solid)
    for kern in (np.ones((1, K)), np.ones((K, 1))):
        bridged |= ndi.binary_closing(solid, kern) & ~solid
    lab, _ = ndi.label(bridged)
    gl = ndi.binary_dilation(glass, np.ones((3, 3)))
    win = np.zeros_like(bridged)
    for j, sl in enumerate(ndi.find_objects(lab), 1):
        comp = lab[sl] == j
        if comp.sum() >= 150 and (gl[sl] & comp).sum() >= P["min_glass_px"]:
            win[sl] |= comp
    return win


def prune_spurs(sk, P):
    for _ in range(4):
        S = Skeleton(sk)
        df = summarize(S, separator="_")
        spurs = df[(df.branch_type == 1) & (df.branch_distance < P["spur"])]
        if len(spurs) == 0:
            break
        for idx in spurs.index:
            for pid, (y, x) in zip(S.path(idx), S.path_coordinates(idx).astype(int)):
                if S.degrees[pid] <= 2:          # keep the junction pixel
                    sk[y, x] = False
    return sk


def vectorise(cls, P):
    union = ndi.binary_closing(cls > 0, np.ones((3, 3)))
    sk = prune_spurs(skeletonize(union), P)
    S = Skeleton(sk)
    segs = []
    for p in range(S.n_paths):
        pc = S.path_coordinates(p)
        if len(pc) < 4:
            continue
        c = cls[pc[:, 0].astype(int), pc[:, 1].astype(int)]
        runs, start = [], 0
        for t in range(1, len(c) + 1):
            if t == len(c) or c[t] != c[start]:
                runs.append((start, t - 1, int(c[start]) or 1))
                start = t
        for s0, s1, kc in runs:
            if kc == 1 and s1 - s0 < 3 and len(runs) > 1:
                continue
            if kc in ((2, 3) if P.get("white_windows") else (2,)) and P.get("door_segments") == "rect":
                kc = -kc          # placeholder: keeps wall pieces connected for the cluster filter, dropped later
                                  # (doors/windows themselves come from door_rects())
            poly = approximate_polygon(pc[max(0, s0 - 1): s1 + 2], tolerance=P["simplify"])
            for q in range(len(poly) - 1):
                (y0, x0), (y1, x1) = poly[q], poly[q + 1]
                segs.append([float(x0), float(y0), float(x1), float(y1), kc])
    # axis snap
    t = P["axis_snap"]
    for s in segs:
        x0, y0, x1, y1, _ = s
        if abs(x1 - x0) > abs(y1 - y0) and abs(y1 - y0) <= t * abs(x1 - x0):
            s[1] = s[3] = (y0 + y1) / 2
        elif abs(y1 - y0) > abs(x1 - x0) and abs(x1 - x0) <= t * abs(y1 - y0):
            s[0] = s[2] = (x0 + x1) / 2
    if not segs:
        return []
    # merge endpoints
    n = len(segs)
    pts = np.array([[s[0], s[1]] for s in segs] + [[s[2], s[3]] for s in segs])
    parent = list(range(len(pts)))

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u
    for u, v in cKDTree(pts).query_pairs(P["endpoint_merge"]):
        parent[find(u)] = find(v)
    groups = {}
    for u in range(len(pts)):
        groups.setdefault(find(u), []).append(u)
    for g in groups.values():
        pts[g] = pts[g].mean(0)
    out = []
    for j, s in enumerate(segs):
        (x0, y0), (x1, y1) = pts[j], pts[j + n]
        if np.hypot(x1 - x0, y1 - y0) >= 4:
            out.append([int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)), s[4]])
    # drop small isolated WALL clusters (doors/windows are often not endpoint-connected yet)
    par = {}

    def fd(u):
        par.setdefault(u, u)
        while par[u] != u:
            u = par[u]
        return u
    for x0, y0, x1, y1, _ in out:
        par[fd((x0, y0))] = fd((x1, y1))
    tot = {}
    for x0, y0, x1, y1, _ in out:
        r = fd((x0, y0))
        tot[r] = tot.get(r, 0) + np.hypot(x1 - x0, y1 - y0)
    # clusters whose bounding box is tiny are furniture outlines (crates, tables), not walls
    ext = P.get("min_cluster_extent", 0)
    bb = {}
    for x0, y0, x1, y1, _ in out:
        r = fd((x0, y0)); b = bb.setdefault(r, [x0, y0, x0, y0])
        b[0] = min(b[0], x0, x1); b[1] = min(b[1], y0, y1); b[2] = max(b[2], x0, x1); b[3] = max(b[3], y0, y1)
    def big(r):
        b = bb[r]; return max(b[2] - b[0], b[3] - b[1]) >= ext
    return [s for s in out if s[4] != 1 or (tot[fd((s[0], s[1]))] >= P["min_cluster"] and big(fd((s[0], s[1]))))]


def door_rects(door):
    """One door segment per door blob, along the blob's long axis (minAreaRect). Skeletonising a
    filled door rectangle gives stubs and zero-length pieces; this gives exactly one clean door,
    and a merged double door (door_merge_gap) stays one door."""
    n, lab = cv2.connectedComponents(door.astype(np.uint8))
    out = []
    for j in range(1, n):
        ys, xs = np.nonzero(lab == j)
        if len(xs) < 50:
            continue
        (cx, cy), (w, h), ang = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
        L = max(w, h) / 2
        t = np.radians(ang if w >= h else ang + 90)
        dx, dy = L * np.cos(t), L * np.sin(t)
        out.append([int(round(cx - dx)), int(round(cy - dy)), int(round(cx + dx)), int(round(cy + dy)), 2])
    return out


def _deg(segs):
    d = {}
    for x0, y0, x1, y1, _ in segs:
        d[(x0, y0)] = d.get((x0, y0), 0) + 1; d[(x1, y1)] = d.get((x1, y1), 0) + 1
    return d


def merge_collinear(segs, max_deg=8.0):
    """Remove degree-2 vertices where two same-kind segments continue in (almost) the same direction.
    Turns the staircase of tiny skeleton segments into long straight walls."""
    changed = True
    while changed:
        changed = False
        deg = _deg(segs); at = {}
        for i, s in enumerate(segs):
            at.setdefault((s[0], s[1]), []).append(i); at.setdefault((s[2], s[3]), []).append(i)
        for v, ids in at.items():
            if deg[v] != 2 or len(ids) != 2:
                continue
            a, b = segs[ids[0]], segs[ids[1]]
            if a is None or b is None or a[4] != b[4] or a[4] != 1:
                continue
            pa = (a[0], a[1]) if (a[2], a[3]) == v else (a[2], a[3])
            pb = (b[0], b[1]) if (b[2], b[3]) == v else (b[2], b[3])
            u1 = np.subtract(v, pa); u2 = np.subtract(pb, v)
            n1, n2 = np.linalg.norm(u1), np.linalg.norm(u2)
            if n1 == 0 or n2 == 0:
                continue
            ang = np.degrees(np.arccos(np.clip(u1 @ u2 / (n1 * n2), -1, 1)))
            # allow bigger bends between very short pieces (curves), strict for long ones
            lim = max_deg if min(n1, n2) > 40 else max_deg * 2
            if ang <= lim:
                segs[ids[0]] = [pa[0], pa[1], pb[0], pb[1], 1]; segs[ids[1]] = None
                segs = [x for x in segs if x is not None]; changed = True
                break
    return segs


def _cross(a, b, c, d):
    def o(p, q, r): return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def connect_doors(segs, r):
    """Every door end gets a wall: link it to the nearest dead-end wall endpoint within r px, else to
    the nearest point on a wall segment. Without this, the jambs leave 10-30px slits beside doors
    (light and vision leak, tokens slip past a closed door)."""
    walls = [x for x in segs if x[4] == 1]
    deg = _deg(segs); out = list(segs)
    for d in [x for x in segs if x[4] in (2, 3)]:
        for e in ((d[0], d[1]), (d[2], d[3])):
            E = np.array(e, float)
            ends = [p for w in walls for p in ((w[0], w[1]), (w[2], w[3])) if deg.get(p, 0) == 1]
            best = None
            if ends:
                dist = [np.hypot(p[0] - E[0], p[1] - E[1]) for p in ends]; j = int(np.argmin(dist))
                if 0 < dist[j] <= r:
                    best = ends[j]; deg[best] = 2
            if best is None:
                bd = r + 1
                for w in walls:
                    A, B = np.array(w[:2], float), np.array(w[2:4], float); AB = B - A; L2 = AB @ AB
                    u = 0 if L2 == 0 else np.clip((E - A) @ AB / L2, 0, 1); c = A + u * AB; dd = np.linalg.norm(c - E)
                    if 0.5 < dd < bd:
                        bd, best = dd, (int(round(c[0])), int(round(c[1])))
            if best is not None:
                out.append([best[0], best[1], int(e[0]), int(e[1]), 1])
            deg[e] = deg.get(e, 0) + 1
    return out


def veto_segments(a, segs, cfg):
    """Drop walls that are clearly not architecture: outside the building box, or sitting on vegetation (vines,
    trees: green dominant) or on page art. cfg = {"box":[x0,y0,x1,y1], "green": 15}."""
    R, G, B = (a[..., i].astype(int) for i in range(3))
    veg = (G - R > cfg.get("green", 15)) & (G - B > 5)
    veg = ndi.uniform_filter(veg.astype(float), 21) > 0.35
    x0, y0, x1, y1 = cfg.get("box", [0, 0, a.shape[1], a.shape[0]])
    out = []
    for s in segs:
        mx, my = (s[0] + s[2]) / 2, (s[1] + s[3]) / 2
        if not (x0 <= mx <= x1 and y0 <= my <= y1):
            continue
        if s[4] == 1 and veg[int(min(max(my, 0), a.shape[0] - 1)), int(min(max(mx, 0), a.shape[1] - 1))]:
            continue
        out.append(s)
    return out


def chain_openings(segs, r):
    """Crenellated walls: windows/doors separated by merlons that the masks miss. From each end of a window or
    door, walk ALONG its axis and connect to the nearest window/door end or wall point ahead within r px
    (angle < ~25 deg). Fills the merlons between window slits and closes window rows into continuous walls."""
    if not r:
        return segs
    ops = [x for x in segs if x[4] in (2, 3)]
    ends = [(np.array(x[:2], float), x) for x in segs] + [(np.array(x[2:4], float), x) for x in segs]
    add = []
    for o in ops:
        A, B = np.array(o[:2], float), np.array(o[2:4], float)
        d = B - A; L = np.linalg.norm(d)
        if L < 1:
            continue
        d /= L
        for E, sgn in ((A, -1), (B, 1)):
            best, bd = None, r + 1
            for P, t in ends:
                if t is o:
                    continue
                v = P - E; dist = np.linalg.norm(v)
                if 3 < dist < bd and (v / dist) @ (sgn * d) > 0.9:
                    best, bd = P, dist
            if best is not None:
                add.append([int(E[0]), int(E[1]), int(best[0]), int(best[1]), 1])
    # dedupe
    seen = set(); out = []
    for a in add:
        k = tuple(sorted([(a[0], a[1]), (a[2], a[3])]))
        if k not in seen:
            seen.add(k); out.append(a)
    return segs + out


def bridge_gaps(segs, gap):
    """Close holes: a dead-end wall endpoint connects to the nearest wall/door point (vertex, or its
    projection onto a segment) within `gap` px, as long as the link roughly continues the wall
    (< 60 deg) or is very short (< gap/3)."""
    if not gap:
        return segs
    deg = _deg(segs)
    ends = [(s, (s[0], s[1]), (s[2], s[3])) for s in segs] + [(s, (s[2], s[3]), (s[0], s[1])) for s in segs]
    added = []
    for s, p, q in ends:
        if deg[p] != 1:
            continue
        p_ = np.array(p, float); dirv = p_ - np.array(q, float)
        dirv /= np.linalg.norm(dirv) + 1e-9
        best, bd = None, gap + 1
        for t in segs:
            if t is s:
                continue
            A, B = np.array(t[:2], float), np.array(t[2:4], float)
            AB = B - A; L2 = AB @ AB
            u = 0 if L2 == 0 else np.clip((p_ - A) @ AB / L2, 0, 1)
            c = A + u * AB; d = np.linalg.norm(c - p_)
            if d < 1 or d >= bd:
                continue
            ok = d < gap / 3 or ((c - p_) / d) @ dirv > 0.5
            if ok:
                best, bd = c, d
        if best is not None and any(_cross(p, best, t[:2], t[2:4]) for t in segs if t[4] == 2):
            best = None                     # never wall off a doorway
        if best is not None:
            added.append([int(p[0]), int(p[1]), int(round(best[0])), int(round(best[1])), 1])
            deg[p] = 2
    return segs + added


def sky_edges(a, cfg):
    """Kind-4 'edge' walls (block movement only) along the border between the map and the sky / void
    (blue sky: B - R > b_minus_r, or transparent). Stops tokens walking off cliffs and balconies whose
    parapets are too thin for the wall mask."""
    R, G, B, A = (a[..., i].astype(int) for i in range(4))
    sky = (A == 0) | ((B - R) > cfg.get("b_minus_r", 35))
    land = (~sky).astype(np.uint8)
    k = cfg.get("open", 15)  # removes lightning bolts, glows and other thin non-blue sky art
    land = cv2.morphologyEx(land, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    # RETR_LIST: also the inner contours = holes in the land (an open courtyard / storm pit inside a building)
    cs, _ = cv2.findContours(land, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    H, W = land.shape
    for c in cs:
        if cv2.contourArea(c) < cfg.get("min_area", 20000):
            continue
        ap = cv2.approxPolyDP(c, cfg.get("simplify", 5), True)[:, 0, :]
        for p, q in zip(ap, np.roll(ap, -1, 0)):
            # skip segments running along the image border (the crop edge is not a cliff)
            if (p[0] == q[0] and p[0] in (0, W - 1)) or (p[1] == q[1] and p[1] in (0, H - 1)):
                continue
            out.append([int(p[0]), int(p[1]), int(q[0]), int(q[1]), 4])
    return out


def apply_fixes(segs, fx):
    for x0, y0, x1, y1 in fx.get("remove_boxes", []):
        segs = [s for s in segs if not (x0 <= min(s[0], s[2]) and max(s[0], s[2]) <= x1
                                         and y0 <= min(s[1], s[3]) and max(s[1], s[3]) <= y1)]
    return segs + [list(map(int, s)) for s in fx.get("add", [])]


def snap_openings(segs, P):
    wp = np.array([[s[0], s[1]] for s in segs if s[4] == 1] + [[s[2], s[3]] for s in segs if s[4] == 1], float)
    if not len(wp):
        return segs
    for s in segs:
        if s[4] == 1:
            continue
        for a, b in ((0, 1), (2, 3)):
            d = np.hypot(wp[:, 0] - s[a], wp[:, 1] - s[b])
            j = d.argmin()
            if 0 < d[j] <= P["door_snap"]:
                s[a], s[b] = int(wp[j, 0]), int(wp[j, 1])
    return segs


def overlay(a, segs, path):
    im = Image.fromarray(a[..., :3].astype(np.uint8))
    d = ImageDraw.Draw(im)
    col = {1: (255, 40, 40), 2: (40, 120, 255), 3: (0, 230, 230), 4: (255, 200, 0)}
    for x0, y0, x1, y1, k in segs:
        d.line([x0, y0, x1, y1], fill=col[k], width=6)
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", help="KEY=path.webp")
    ap.add_argument("--out", default="walls.json")
    ap.add_argument("--profile", help="profiles.json[:name] overriding DEFAULT_PROFILE keys")
    ap.add_argument("--fixes", help="fixes.json with per-key remove_boxes / add")
    ap.add_argument("--sample", action="append", help="x,y point (repeatable): print mean/std RGB (7x7) and exit")
    args = ap.parse_args()
    P = load_profile(args.profile)
    fixes = json.load(open(args.fixes)) if args.fixes else {}
    outdir = os.path.dirname(os.path.abspath(args.out))
    result = {}
    for spec in args.images:
        key, _, path = spec.partition("=")
        a = np.array(Image.open(path).convert("RGBA"))
        if args.sample is not None:
            for pt in args.sample:
                x, y = map(int, pt.split(","))
                p = a[y - 3:y + 4, x - 3:x + 4, :3].reshape(-1, 3).astype(int)
                print(key, (x, y), "mean", p.mean(0).astype(int).tolist(), "std", p.std(0).astype(int).tolist())
            continue
        wall_raw, door_raw, glass = colour_masks(a, P)
        door = clean_doors(door_raw, P)
        ww = None
        if P.get("white_windows"):
            # white slits between merlons: count them as wall BEFORE cleaning, so a crenellated wall is one
            # connected band (otherwise each merlon is a small blob and gets dropped)
            ww = white_windows(door_raw, wall_raw, P) & ~door
            wall_raw = wall_raw | ndi.binary_dilation(ww, iterations=P.get("white_window_join", 8))
        wall = clean_walls(wall_raw, P)
        if P.get("dark_bands"):
            wall = wall | dark_bands(a, P["dark_bands"], wall_raw if P["dark_bands"].get("with_stone") else None)
        if P.get("sandwich"):
            sw = sandwich_walls(a, P["sandwich"]) & ~ndi.binary_dilation(door_raw, iterations=4)
            wall = wall | sw
        if P.get("suppress_white_blobs"):
            wall = wall & ~white_blob_zone(door_raw, P["suppress_white_blobs"])
        win = find_windows(wall | door, glass, P)
        if ww is not None:
            win |= ww
        cls = np.zeros(wall.shape, np.uint8)
        cls[wall] = 1
        cls[win] = 3
        cls[door] = 2
        segs = vectorise(cls, P)
        segs = [x for x in segs if x[4] > 0]
        if P.get("door_segments") == "rect":
            segs += door_rects(door)
            if P.get("white_windows"):
                segs += [x[:4] + [3] for x in door_rects(ww)]
        if P.get("merge_collinear"):
            segs = merge_collinear(segs, P["merge_collinear"])
        if P.get("door_connect"):
            segs = connect_doors(segs, P["door_connect"])
        segs = chain_openings(segs, P.get("chain_openings", 0))
        segs = bridge_gaps(segs, P.get("bridge_gap", 0))
        if P.get("veto"):
            segs = veto_segments(a, segs, P["veto"])
        if P.get("sky_edge"):
            segs += sky_edges(a, P["sky_edge"])
        segs = apply_fixes(segs, fixes.get(key, {}))
        segs = snap_openings(segs, P)
        result[key] = segs
        overlay(a, segs, os.path.join(outdir, f"overlay-{key}.png"))
        counts = {n: sum(1 for s in segs if s[4] == k) for k, n in ((1, "walls"), (2, "doors"), (3, "windows"), (4, "edges"))}
        print(key, path, counts)
    if args.sample is None:
        json.dump(result, open(args.out, "w"), separators=(",", ":"))
        print("wrote", args.out)


if __name__ == "__main__":
    main()
