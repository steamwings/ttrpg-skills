#!/usr/bin/env python3
"""Walls from ROOM FLOORS, for maps whose walls are not a distinct colour
(e.g. Loomlurch: rooms carved into a tree, walls = bark + black outline).

Instead of finding wall pixels, find the interior FLOOR regions by colour, let a human/Claude
pick which regions are real rooms, and wall their outlines. Doors = white rectangles next to a
room; wall outlines are cut where a door sits and stitched to the door ends.

Stage 1 — label candidates (writes <outdir>/rooms-labels.png with region ids):
  detect_rooms.py label map.webp --outdir work/ [--floor R-G:8:40,G-B:22:,R:70:200] [--min-area 12000]

Stage 2 — build walls from the chosen regions:
  detect_rooms.py build map.webp --outdir work/ --keep 174,230,306 --rect 230,508 [--circle 306]
      --out work/walls.json
  --rect / --circle force a clean rectangle (minAreaRect) or circle (minEnclosingCircle) for rooms
  whose floor mask is ragged (furniture, shadows). Anything with rect-fit > 0.82 or circle-fit > 0.80
  gets that automatically; everything else keeps its smoothed contour.

Output walls.json in the same format as detect_walls.py: {"L": [[x0,y0,x1,y1,kind],...]} in image px.
Keep the chosen ids/flags in an examples/<map>-rooms.json so the run is reproducible.
Overlay: <outdir>/rooms-overlay.png (red walls, blue doors). Review it before pushing.
"""
import argparse, json, os
import numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image, ImageDraw


def parse_floor(spec):
    rules = []
    for part in spec.split(","):
        name, lo, hi = part.split(":")
        rules.append((name, int(lo) if lo else None, int(hi) if hi else None))
    return rules


def floor_mask(a, rules, min_area):
    b = cv2.medianBlur(a, 9).astype(int)
    ch = {"R": b[..., 0], "G": b[..., 1], "B": b[..., 2]}
    m = np.ones(a.shape[:2], bool)
    for name, lo, hi in rules:
        v = ch[name[0]] - ch[name[2]] if "-" in name else ch[name]
        if lo is not None: m &= v >= lo
        if hi is not None: m &= v <= hi
    m = ndi.binary_opening(m, np.ones((9, 9)))
    m = ndi.binary_closing(m, np.ones((9, 9)))
    m = ndi.binary_fill_holes(m)
    lab, k = ndi.label(m)
    sz = ndi.sum(m, lab, range(1, k + 1))
    keep = np.zeros(k + 1, bool); keep[1:] = sz > min_area
    return np.where(keep[lab], lab, 0)


def find_doors(a, rooms, near_px=18, min_px=400):
    white = (a[..., 0] > 230) & (a[..., 1] > 230) & (a[..., 2] > 225)
    white = ndi.binary_opening(white, np.ones((5, 5)))
    near = ndi.binary_dilation(rooms, iterations=near_px)
    L, _ = ndi.label(white)
    blobs, doors = [], []
    for j, sl in enumerate(ndi.find_objects(L), 1):
        comp = L[sl] == j
        ys, xs = np.nonzero(comp); ys = ys + sl[0].start; xs = xs + sl[1].start
        if len(xs) >= 300:
            blobs.append((xs.mean(), ys.mean()))
        if len(xs) < min_px or not near[ys, xs].any():
            continue
        pts = np.stack([xs, ys], 1).astype(float); c = pts.mean(0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        d = vt[0]; pr = (pts - c) @ d
        doors.append({"c": c, "d": d, "p0": c + d * pr.min(), "p1": c + d * pr.max()})
    # callout / map-edge DASHED lines look exactly like doors (~48x17 white bars): drop a candidate
    # if another white blob sits 55-120px away along its own axis.
    B = np.array(blobs)
    out = []
    for r in doors:
        v = B - r["c"]; dist = np.linalg.norm(v, axis=1)
        along = np.abs(v @ r["d"]) / np.maximum(dist, 1e-9)
        if not ((dist > 55) & (dist < 120) & (along > 0.9)).any():
            out.append(r)
    return out


def room_outline(mask, force):
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    m0 = cv2.morphologyEx(np.pad(mask, 40).astype(np.uint8), cv2.MORPH_CLOSE, disk)[40:-40, 40:-40] > 0
    m0 = ndi.binary_fill_holes(m0)
    m = ndi.binary_dilation(m0, iterations=6).astype(np.uint8)   # push out onto the wall line
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    area = m.sum(); big = max(cs, key=len)
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(big)
    (ex, ey), er = cv2.minEnclosingCircle(big)
    rfit, cfit = area / (rw * rh), area / (np.pi * er * er)
    if force == "rect" or (force is None and rfit > 0.82):
        box = cv2.boxPoints(((cx, cy), (rw, rh), ang))
        pts = np.concatenate([np.linspace(box[i], box[(i + 1) % 4], int(max(2, np.linalg.norm(box[(i + 1) % 4] - box[i]))))
                              for i in range(4)])
        return [pts], "rect"
    if force == "circle" or (force is None and cfit > 0.80):
        t = np.linspace(0, 2 * np.pi, int(2 * np.pi * er), endpoint=False)
        return [np.stack([ex + er * np.cos(t), ey + er * np.sin(t)], 1)], "circle"
    return [c[:, 0, :].astype(float) for c in cs if len(c) >= 50], "contour"


def build(a, lab, keep, rects, circles, eps=5.0):
    doors = find_doors(a, np.isin(lab, keep))
    boxes = [((r["p0"] + r["p1"]) / 2, r["d"], np.array([-r["d"][1], r["d"][0]]), np.linalg.norm(r["p1"] - r["p0"]) / 2)
             for r in doors]

    def in_door(p):
        for c, d, n, h in boxes:
            v = p - c
            if abs(v @ d) <= h + 6 and abs(v @ n) <= 22:
                return True
        return False
    segs, cut_ends = [], []
    for j in keep:
        if not (lab == j).any():
            print(f"warning: region {j} not in rooms-labels.npy (ids change between label runs)"); continue
        force = "rect" if j in rects else "circle" if j in circles else None
        outlines, shape = room_outline(lab == j, force)
        for pts in outlines:
            flags = np.array([in_door(p) for p in pts])
            if flags.all():
                continue
            s = int(np.argmax(~flags)); pts = np.roll(pts, -s, 0); flags = np.roll(flags, -s)
            pts = np.vstack([pts, pts[:1]]); flags = np.append(flags, flags[0])
            runs, cur = [], []
            for p, f in zip(pts, flags):
                if not f: cur.append(p)
                else:
                    if len(cur) > 1: runs.append(np.array(cur))
                    cur = []
            if len(cur) > 1: runs.append(np.array(cur))
            for run in runs:
                ap = cv2.approxPolyDP(run.astype(np.float32).reshape(-1, 1, 2), eps, False)[:, 0, :]
                segs += [[*p.tolist(), *q.tolist(), 1] for p, q in zip(ap[:-1], ap[1:])]
                if len(runs) > 1 or flags.any():
                    cut_ends += [run[0], run[-1]]
    dends = []
    for c, d, n, h in boxes:
        p, q = c - d * (h + 3), c + d * (h + 3)
        segs.append([*p.tolist(), *q.tolist(), 2]); dends += [p, q]
    dends = np.array(dends) if dends else np.zeros((0, 2))
    for e in cut_ends:                                  # stitch cut wall ends to the door ends
        if not len(dends): break
        dist = np.linalg.norm(dends - e, axis=1); k = dist.argmin()
        if dist[k] <= 35:
            segs.append([*e.tolist(), *dends[k].tolist(), 1])
    out = [[int(round(v)) for v in s[:4]] + [s[4]] for s in segs]
    return [s for s in out if (s[0], s[1]) != (s[2], s[3])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["label", "build"])
    ap.add_argument("image")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--floor", default="R-G:8:40,G-B:22:,R:70:200",
                    help="comma list NAME:lo:hi on the 9px-median image; NAME = R,G,B or X-Y differences")
    ap.add_argument("--min-area", type=int, default=12000)
    ap.add_argument("--keep", default=""); ap.add_argument("--rect", default=""); ap.add_argument("--circle", default="")
    ap.add_argument("--key", default="L"); ap.add_argument("--out", default="walls.json")
    a_ = ap.parse_args()
    os.makedirs(a_.outdir, exist_ok=True)
    a = np.array(Image.open(a_.image).convert("RGB"))
    labpath = os.path.join(a_.outdir, "rooms-labels.npy")
    if a_.stage == "label":
        lab = floor_mask(a, parse_floor(a_.floor), a_.min_area)
        np.save(labpath, lab)
        s = 1000 / a.shape[1]
        ov = a.copy(); m = lab > 0
        ov[m] = (ov[m] * 0.45 + np.array([255, 0, 255]) * 0.55).astype(np.uint8)
        im = Image.fromarray(ov).resize((1000, int(a.shape[0] * s))); d = ImageDraw.Draw(im)
        for j in np.unique(lab)[1:]:
            ys, xs = np.nonzero(lab[::4, ::4] == j)
            d.text((xs.mean() * 4 * s, ys.mean() * 4 * s), str(j), fill=(255, 255, 0))
        im.save(os.path.join(a_.outdir, "rooms-labels.png"))
        print("regions:", len(np.unique(lab)) - 1, "->", os.path.join(a_.outdir, "rooms-labels.png"))
        return
    lab = np.load(labpath)
    ids = lambda s: [int(x) for x in s.split(",") if x]
    segs = build(a, lab, ids(a_.keep), set(ids(a_.rect)), set(ids(a_.circle)))
    json.dump({a_.key: segs}, open(a_.out, "w"), separators=(",", ":"))
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    for x0, y0, x1, y1, k in segs:
        d.line([x0, y0, x1, y1], fill=(255, 40, 40) if k == 1 else (40, 120, 255), width=7)
    im.save(os.path.join(a_.outdir, "rooms-overlay.png"))
    print({"walls": sum(s[4] == 1 for s in segs), "doors": sum(s[4] == 2 for s in segs)}, "->", a_.out)


if __name__ == "__main__":
    main()
