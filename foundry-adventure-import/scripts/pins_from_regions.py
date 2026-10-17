#!/usr/bin/env python3
"""pins_from_regions.py ADVENTURE.json CHAPTER BOOK_MAP_SUFFIX ALIGN.json CONFIG.json SCENE_ID OUT.json [LEVEL=FILE ...]

Turn a 5etools map image's `mapRegions` into pins for create-area-notes.js.
- BOOK_MAP_SUFFIX: end of the image href path (e.g. 062-map-3.2-loomlurch.webp)
- ALIGN.json: align_maps.py output (book -> each scene image)
- CONFIG.json: the chapter's converter config (journal id + page_ids "area:<id>")
- LEVEL=FILE: map an align key (scene image file used for aligning) to the Level background file name in Foundry;
  default: the align key itself.
Each region centroid goes to the image whose crop holds it with the largest margin, clamped 40px inside the image.
Also writes the region polygon (in scene-image pixels) so tokens can be spread inside it (place-tokens.js).
"""
import json, sys
import numpy as np
from PIL import Image


def main(adv, chapter, suffix, align, cfg, scene, out, *levels):
    data = json.load(open(adv))
    data = data["adventureData"][0]["data"] if "adventureData" in data else data["data"]
    ch = data[int(chapter)]
    cfg = json.load(open(cfg))
    al = json.load(open(align))
    lvmap = dict(l.split("=", 1) for l in levels)
    names, img = {}, None

    def walk(e):
        nonlocal img
        if isinstance(e, dict):
            if e.get("id") and e.get("name"): names[e["id"]] = e["name"]
            if e.get("href", {}).get("path", "").endswith(suffix): img = e
            for v in e.values(): walk(v)
        elif isinstance(e, list):
            for x in e: walk(x)
    walk(ch)
    sizes = {k: Image.open(k).size for k in al}
    pins = []
    for r in img["mapRegions"]:
        P = np.array(r["points"], float)
        best = None
        for lv, info in al.items():
            M = np.array(info["M"]); q = M[:, :2] @ P.mean(0) + M[:, 2]
            w, h = sizes[lv]
            margin = min(q[0], q[1], w - q[0], h - q[1])
            if best is None or margin > best[0]: best = (margin, lv, M, w, h)
        _, lv, M, w, h = best
        poly = (P @ M[:, :2].T + M[:, 2]).round().astype(int).tolist()
        c = M[:, :2] @ P.mean(0) + M[:, 2]
        name = names.get(r["area"], "?")
        pins.append({"area": r["area"], "label": name.split(".")[0], "name": name,
                     "page": cfg.get("page_ids", {}).get(f"area:{r['area']}"),
                     "level": lvmap.get(lv, lv.split("/")[-1]),
                     "x": int(min(max(c[0], 40), w - 40)), "y": int(min(max(c[1], 40), h - 40)), "poly": poly})
    # keep pins apart (insets put several areas' centroids close together)
    for i, p in enumerate(pins):
        for q in pins[:i]:
            if abs(p["x"] - q["x"]) < 80 and abs(p["y"] - q["y"]) < 80 and p["level"] == q["level"]:
                p["x"] = int(min(p["x"] + 90, sizes[next(iter(sizes))][0] - 40)); p["y"] += 40
    missing = [p["label"] for p in pins if not p["page"]]
    json.dump({"scene": scene, "journal": cfg["journal"]["id"], "pins": pins}, open(out, "w"), indent=1)
    print(f"{len(pins)} pins -> {out}" + (f"; no page for {missing}" if missing else ""))


if __name__ == "__main__":
    main(*sys.argv[1:])
