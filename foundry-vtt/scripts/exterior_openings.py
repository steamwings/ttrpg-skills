#!/usr/bin/env python3
"""Find EXTERIOR doors and windows (one side indoors, the other outdoors) from a walls.json and
return a point just outside each one, where an exterior light goes (a lantern by the door, window
glow spilling out at night).

  exterior_openings.py walls.json --size 3800x5300 --out openings.json [--key L] [--overlay L=map.webp]

Indoors = rasterised walls (doors and windows included), closed (31px) to seal small leaks, then
hole-filled. Output: {"KEY": [[x, y, kind], ...]} in image px, kind 2 = door, 3 = window.
"""
import argparse, json, os
import numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("walls"); ap.add_argument("--size", required=True)
    ap.add_argument("--out", default="openings.json"); ap.add_argument("--key", nargs="*")
    ap.add_argument("--overlay", nargs="*", default=[]); ap.add_argument("--probe", type=int, default=45)
    ap.add_argument("--offset", type=int, default=60, help="px outside the opening to place the light")
    a = ap.parse_args()
    W, H = map(int, a.size.lower().split("x"))
    walls = json.load(open(a.walls)); overlays = dict(o.split("=", 1) for o in a.overlay)
    out = {}
    for key in a.key or walls:
        m = np.zeros((H, W), np.uint8)
        for x0, y0, x1, y1, _ in walls[key]:
            cv2.line(m, (x0, y0), (x1, y1), 1, 9)
        inside = ndi.binary_fill_holes(ndi.binary_closing(m > 0, np.ones((31, 31))))
        pts = []
        for x0, y0, x1, y1, k in walls[key]:
            if k == 1:
                continue
            c = np.array([(x0 + x1) / 2, (y0 + y1) / 2]); d = np.array([x1 - x0, y1 - y0], float)
            d /= np.linalg.norm(d) + 1e-9; n = np.array([-d[1], d[0]])
            side = []
            for sgn in (1, -1):
                p = (c + sgn * n * a.probe).round().astype(int)
                ok = 0 <= p[0] < W and 0 <= p[1] < H
                side.append(bool(inside[p[1], p[0]]) if ok else False)
            if side[0] != side[1]:
                sgn = -1 if side[0] else 1                     # towards the outside
                q = (c + sgn * n * a.offset).round().astype(int)
                pts.append([int(q[0]), int(q[1]), int(k)])
        out[key] = pts
        print(key, len(pts), "exterior openings")
        if key in overlays:
            im = cv2.cvtColor(np.array(Image.open(overlays[key]).convert("RGB")), cv2.COLOR_RGB2BGR)
            im[inside] = (im[inside] * 0.6 + np.array([255, 0, 255]) * 0.4).astype(np.uint8)
            for x, y, k in pts:
                cv2.circle(im, (x, y), 22, (0, 200, 255) if k == 2 else (255, 255, 0), -1)
            p = os.path.join(os.path.dirname(os.path.abspath(a.out)), f"openings-{key}.png")
            cv2.imwrite(p, cv2.resize(im, (im.shape[1] // 3, im.shape[0] // 3)))
    json.dump(out, open(a.out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
