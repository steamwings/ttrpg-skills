#!/usr/bin/env python3
"""scene_from_spec.py SPEC.json OUT_DIR — a play-ready single-level scene from a hand-written spec.

For supplement maps without 5etools mapRegions and where auto-walls doesn't fit: trace each keyed room by eye
(on a downscaled crop, then map back with `crop` = [x0, y0, scale]) and describe it once:

{"name": "The Never Landing", "folder": ["Witchlight", "Thither"], "image": "local.webp", "src": "assets/maps/...",
 "width": 5120, "height": 3360, "grid": {"size": 160, "distance": 5}, "darkness": 0.3, "journal": "<id>",
 "page": "<page id or null>", "crop": [3700, 350, 2.0833],
 "rooms": [{"label": "C2", "name": "C2. Captain's Quarters", "page": "<page id>", "poly": [[x, y], ...], "walls": true,
            "doors": [[x0, y0, x1, y1]], "secret": [[...]], "interior": true, "pin": [x, y],
            "lights": [{"at": [x, y], "dim": 20, "bright": 10, "color": "#ffb060"}]}],
 "areas": [{"label": "C1", ...same without walls}], "tokens": [{"area": "C2", "actor": "Actor.<id>", "count": 1, "linked": true}]}

Coordinates in `rooms`/`areas` are crop coordinates when `crop` is set on the room or the spec, else image px.
Doors must lie on a polygon edge; that edge is split around them. Writes OUT_DIR/scene.json (for build-scene.js),
pins.json (create-area-notes.js / plan_tokens.py) and tokens-spec.json.
"""
import json, math, pathlib, sys


def to_img(pt, crop):
    if not crop: return [round(pt[0]), round(pt[1])]
    x0, y0, s = crop
    return [round(x0 + pt[0] * s), round(y0 + pt[1] * s)]


def on_segment(a, b, p, tol=6):
    ax, ay = a; bx, by = b; px, py = p
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    if L2 == 0: return None
    t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L2
    d = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / math.sqrt(L2)
    return t if d <= tol and -0.01 <= t <= 1.01 else None


def clear_doorways(walls, tol=15):
    """Rooms that share a wall each draw it: cut every plain wall where it overlaps a door, drop exact duplicates."""
    doors = [w for w in walls if w[4] != 1]
    out = []
    for w in walls:
        if w[4] != 1: continue
        a, b = w[:2], w[2:4]
        cuts = []
        for d in doors:
            t0, t1 = on_segment(a, b, d[:2], tol), on_segment(a, b, d[2:4], tol)
            if t0 is not None and t1 is not None: cuts.append(sorted((max(0, t0), min(1, t1))))
        t = 0
        for c0, c1 in sorted(cuts) + [(1, 1)]:
            if c0 - t > 1e-3:
                seg = [round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t),
                       round(a[0] + (b[0] - a[0]) * c0), round(a[1] + (b[1] - a[1]) * c0), 1]
                if seg[:4] != seg[2:4] + seg[:2]: out.append(seg)
            t = max(t, c1)
    seen, res = set(), []
    for w in out + doors:
        k = tuple(sorted([tuple(w[:2]), tuple(w[2:4])])) + (w[4],)
        if k not in seen: seen.add(k); res.append(w)
    return res


def main(spec_path, out_dir):
    spec = json.load(open(spec_path)); out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    walls, interiors, lights, pins = [], [], [], []
    for room in spec.get("rooms", []) + spec.get("areas", []):
        crop = room.get("crop", spec.get("crop"))
        poly = [to_img(p, crop) for p in room["poly"]]
        doors = [to_img(d[:2], crop) + to_img(d[2:], crop) for d in room.get("doors", [])]
        secret = [to_img(d[:2], crop) + to_img(d[2:], crop) for d in room.get("secret", [])]   # secret doors (kind 5)
        doors += secret
        if room.get("walls", "doors" in room or room in spec.get("rooms", [])):
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                cuts = []
                for d in doors:
                    t0, t1 = on_segment(a, b, d[:2], 12 * (crop[2] if crop else 1)), on_segment(a, b, d[2:], 12 * (crop[2] if crop else 1))
                    if t0 is not None and t1 is not None: cuts.append(sorted((max(0, t0), min(1, t1))))
                cuts.sort()
                t = 0
                for c0, c1 in cuts + [(1, 1)]:
                    if c0 > t:
                        walls.append([round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t),
                                      round(a[0] + (b[0] - a[0]) * c0), round(a[1] + (b[1] - a[1]) * c0), 1])
                    t = max(t, c1)
            walls += [d + [5 if d in secret else 2] for d in doors]
        if room.get("interior"): interiors.append(poly)
        for l in room.get("lights", []):
            lights.append({**l, "at": to_img(l["at"], crop)})
        pin = to_img(room["pin"], crop) if room.get("pin") else [round(sum(p[0] for p in poly) / len(poly)), round(sum(p[1] for p in poly) / len(poly))]
        pins.append({"label": room["label"], "name": room["name"], "page": room.get("page"), "level": spec["src"].split("/")[-1],
                     "x": pin[0], "y": pin[1], "poly": poly})
    walls = clear_doorways(walls)
    scene = {k: spec[k] for k in ("name", "folder", "src", "width", "height", "grid", "darkness") if k in spec}
    scene.update({"image": spec.get("image"), "journal": spec.get("journal"), "page": spec.get("page"),
                  "walls": walls, "interiors": interiors, "lights": lights, "global": spec.get("global", True)})
    (out / "scene.json").write_text(json.dumps(scene, indent=1))
    (out / "pins.json").write_text(json.dumps({"scene": spec["name"], "journal": spec.get("journal"), "pins": pins}, indent=1))
    (out / "tokens-spec.json").write_text(json.dumps(spec.get("tokens", []), indent=1))
    print(f"{spec['name']}: {len(walls)} walls ({sum(w[4] == 2 for w in walls)} doors), {len(interiors)} interiors, "
          f"{len(lights)} lights, {len(pins)} pins")


if __name__ == "__main__":
    main(*sys.argv[1:3])
