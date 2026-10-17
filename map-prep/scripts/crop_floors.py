#!/usr/bin/env python3
"""Crop one or more map floors so their grids start exactly at (0,0), all share the same
canvas size, and the grid pitch is exactly TARGET px. Required for Foundry V14 Level textures,
which always fill the whole scene (no per-level x/y/size).

  crop_floors.py config.json

config.json
-----------
{
  "target_pitch": 100,                 # px per square in the output (Foundry grid size)
  "frame": [2100, 1700],               # output size in px (multiple of target_pitch). Required
                                       # for >1 floor; for one floor defaults to the full grid.
  "anchor_out": [650, 350],            # where the shared anchor feature lands in the output (px)
  "floors": [
    {"src": "page-41.png", "out": "bavlornas-cottage-l1.webp",
     "box": [120, 300, 2400, 2100],    # optional: region with the grid, for measuring (src px)
     "anchor": [812, 655]},            # optional: shared feature (e.g. stairwell centre), src px
    {"src": "page-42.png", "out": "bavlornas-cottage-l2.webp", "anchor": [1540, 770]}
  ]
}

Without anchors, the crop starts at the first full grid square inside `box` (or the image).
With anchors, every floor is positioned so its anchor lands on `anchor_out`, then snapped to
the grid phase, so the same stair ends up on the same squares on every floor.
Areas outside the source become transparent (webp keeps alpha).
Re-check each output with grid_phase.py: expect pitch ~= target and phase ~= 0.
"""
import json, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_phase import profile, pitch_phase  # noqa: E402


def measure(im, box):
    g = im.convert("L")
    ox = oy = 0
    if box:
        ox, oy = box[0], box[1]
        g = g.crop(tuple(box))
    a = np.asarray(g, float)
    px, phx, _ = pitch_phase(profile(a, 0), 40, 300)
    py, phy, _ = pitch_phase(profile(a, 1), 40, 300)
    return px, py, (phx + ox + 0.5) % px, (phy + oy + 0.5) % py


def main():
    cfg = json.load(open(sys.argv[1]))
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    T = cfg.get("target_pitch", 100)
    floors = cfg["floors"]
    if len(floors) > 1 and "frame" not in cfg:
        sys.exit("frame is required when cropping several floors")
    for f in floors:
        src = Image.open(os.path.join(base, f["src"])).convert("RGBA")
        px, py, phx, phy = measure(src, f.get("box"))
        sx, sy = T / px, T / py
        if "anchor" in f:
            ax, ay = cfg["anchor_out"]
            ox, oy = f["anchor"][0] - ax / sx, f["anchor"][1] - ay / sy
        else:
            b = f.get("box", [0, 0])
            ox, oy = b[0], b[1]
        # snap origin to the nearest grid line (ceil when no anchor, so the first square is whole)
        rnd = np.round if "anchor" in f else np.ceil
        ox = phx + rnd((ox - phx) / px) * px
        oy = phy + rnd((oy - phy) / py) * py
        if "frame" in cfg:
            W, H = cfg["frame"]
        else:
            x1 = f.get("box", [0, 0, src.width, src.height])[2]
            y1 = f.get("box", [0, 0, src.width, src.height])[3]
            W = int((x1 - ox) // px) * T
            H = int((y1 - oy) // py) * T
        # affine crop+scale with transparent padding
        out = src.transform((W, H), Image.AFFINE, (1 / sx, 0, ox, 0, 1 / sy, oy),
                            resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
        dst = os.path.join(base, f["out"])
        out.save(dst, "WEBP", quality=88, method=6)
        print(json.dumps({"out": f["out"], "src_pitch": [round(px, 2), round(py, 2)],
                          "origin_src": [round(ox, 1), round(oy, 1)], "size": [W, H]}))


if __name__ == "__main__":
    main()
