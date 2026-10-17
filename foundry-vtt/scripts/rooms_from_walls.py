#!/usr/bin/env python3
"""Find rooms (closed spaces between walls/doors) from a walls.json, for lighting and interior regions.

  rooms_from_walls.py walls.json --size 2100x1700 --out rooms.json [--min-area 6000] [--key L2 ...]
      [--overlay floor.webp]  (writes rooms-<KEY>.png next to --out for review)

walls.json: {"KEY": [[x0,y0,x1,y1,kind], ...]} in image px (detect_walls.py / detect_rooms.py output).
Walls AND doors split rooms (closed doors). Windows too. The outside is whatever touches the image
border and is dropped. Output: {"KEY": [{"c":[x,y], "r":px, "area":px2, "poly":[x0,y0,...]}, ...]}
r = radius of a circle with the room's area. Use it to size lights.
Small leaks in the walls merge a room with the outside. Look at the overlay, and if a room is
missing, close the gap in the walls (fixes file) and re-run.
"""
import argparse, json, os
import numpy as np, cv2
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("walls"); ap.add_argument("--size", required=True)
    ap.add_argument("--out", default="rooms.json"); ap.add_argument("--min-area", type=int, default=6000)
    ap.add_argument("--key", nargs="*"); ap.add_argument("--overlay", nargs="*", default=[])
    ap.add_argument("--thick", type=int, default=9, help="px width when rasterising walls")
    a = ap.parse_args()
    W, H = map(int, a.size.lower().split("x"))
    walls = json.load(open(a.walls))
    overlays = dict(o.split("=", 1) for o in a.overlay)
    out = {}
    for key in a.key or walls:
        m = np.zeros((H, W), np.uint8)
        for x0, y0, x1, y1, _ in walls[key]:
            cv2.line(m, (x0, y0), (x1, y1), 255, a.thick)
        n, lab, stats, cent = cv2.connectedComponentsWithStats((m == 0).astype(np.uint8), connectivity=4)
        border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
        rooms = []
        for j in range(1, n):
            if j in border or stats[j, cv2.CC_STAT_AREA] < a.min_area:
                continue
            mask = (lab == j).astype(np.uint8)
            cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            poly = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 6, True)[:, 0, :]
            # light position: the interior point farthest from walls (centroid can fall outside L-shapes)
            dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
            yx = np.unravel_index(dt.argmax(), dt.shape)
            area = int(stats[j, cv2.CC_STAT_AREA])
            rooms.append({"c": [int(yx[1]), int(yx[0])], "r": int(np.sqrt(area / np.pi)), "area": area,
                          "poly": poly.flatten().astype(int).tolist()})
        out[key] = rooms
        print(key, len(rooms), "rooms")
        if key in overlays:
            im = cv2.cvtColor(np.array(Image.open(overlays[key]).convert("RGB")), cv2.COLOR_RGB2BGR)
            for i, r in enumerate(rooms):
                p = np.array(r["poly"]).reshape(-1, 2)
                cv2.polylines(im, [p], True, (255, 0, 255), 6)
                cv2.circle(im, tuple(r["c"]), 14, (0, 200, 255), -1)
                cv2.putText(im, str(i), (r["c"][0] + 18, r["c"][1]), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 255), 3)
            p = os.path.join(os.path.dirname(os.path.abspath(a.out)), f"rooms-{key}.png")
            cv2.imwrite(p, cv2.resize(im, (im.shape[1] // 2, im.shape[0] // 2)))
    json.dump(out, open(a.out, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
