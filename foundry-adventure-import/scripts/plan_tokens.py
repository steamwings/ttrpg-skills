#!/usr/bin/env python3
"""plan_tokens.py PINS.json SPEC.json OUT.json --grid 100 [--sizes sizes.json]

Spread the creatures the text puts in each keyed area over grid cells inside that area's polygon.
PINS.json: pins_from_regions.py output (area label, level, pin x/y, polygon in scene-image px).
SPEC.json: [{"area": "B10", "actor": "Actor.<id>" | "Compendium....", "count": 2, "linked": false, "level": "file.webp"?,
            "note": "why"}]; `level` overrides the pin's level (an area drawn on two floors).
Cells are ordered by distance from the area's centroid, skipping the cell under the pin, so tokens cluster in the
room and never sit on the label. Output: {scene, tokens: [{actor, x, y, level, size, linked}]} with x/y = token
top-left in image px (place-tokens.js adds the scene offset).
"""
import argparse, json
import numpy as np


def inside(poly, x, y):
    n, c = len(poly), False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pins"); ap.add_argument("spec"); ap.add_argument("out")
    ap.add_argument("--grid", type=int, default=100)
    ap.add_argument("--sizes", default=None, help='{"Actor.x": 2} footprint in cells for large creatures')
    a = ap.parse_args()
    pins = json.load(open(a.pins)); spec = json.load(open(a.spec))
    sizes = json.load(open(a.sizes)) if a.sizes else {}
    g = a.grid
    by_area = {}
    for p in pins["pins"]:
        by_area.setdefault(p["label"], []).append(p)
    used, tokens = set(), []
    for s in spec:
        regions = by_area[s["area"]]
        if s.get("level"): regions = [r for r in regions if r["level"] == s["level"]] or regions
        size = sizes.get(s["actor"], 1)
        cells = []
        for r in regions:
            P = np.array(r["poly"]); c = P.mean(0)
            x0, y0 = (P.min(0) // g).astype(int); x1, y1 = (P.max(0) // g).astype(int)
            pin_cell = (r["x"] // g, r["y"] // g)
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    ok = all(inside(r["poly"], (cx + i + .5) * g, (cy + j + .5) * g) for i in range(size) for j in range(size))
                    if not ok or any((cx + i, cy + j) == pin_cell for i in range(size) for j in range(size)): continue
                    cells.append((np.hypot((cx + size / 2) * g - c[0], (cy + size / 2) * g - c[1]), cx, cy, r["level"]))
        cells.sort()
        placed = 0
        for _, cx, cy, lv in cells:
            foot = {(lv, cx + i, cy + j) for i in range(size) for j in range(size)}
            if foot & used: continue
            used |= foot
            tokens.append({"actor": s["actor"], "x": cx * g, "y": cy * g, "level": lv, "size": size,
                           "linked": s.get("linked", False), "area": s["area"]})
            placed += 1
            if placed == s.get("count", 1): break
        if placed < s.get("count", 1):
            print(f"warning: {s['area']} {s['actor']}: room for {placed}/{s.get('count', 1)}")
    json.dump({"scene": pins["scene"], "tokens": tokens}, open(a.out, "w"), indent=1)
    print(f"{len(tokens)} tokens -> {a.out}")


if __name__ == "__main__":
    main()
