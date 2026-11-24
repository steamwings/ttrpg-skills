"""Features: the things a layout places (a well, a causeway, hummocks, a stand of trees).

Each feature reads its spec entry (positions and sizes in grid squares) and can hook into the render:

  heights(ctx)          [(priority, fn(h) -> h), ...]: terrain shaping, applied in priority order
                        (10 raise focal ground, 20 paths, 30 dig/moat, 40 biome edge, 50 scattered relief)
  footprint(ctx)        distance field (px) from the feature's edge, for features with a `role`
                        ("focal" or "path"); biomes keep decoration clear of them
  water_fx(ctx, img, water)   tint or ripple the water near it
  draw(ctx, L)          paint into the layer stack; features draw sorted by `draw_order`
  scene(ctx)            add walls / lights / interiors to ctx.scene (build-scene.js format)

A biome decides which hooks it calls. Register new types with @feature("name").
"""
import math

import numpy as np
from PIL import Image

from .core import catmull, fbm, jitter_poly, mix, polyline_dist, smooth, vary

REGISTRY = {}


def feature(name):
    def deco(cls):
        cls.type = name
        REGISTRY[name] = cls
        return cls
    return deco


def build(spec_features, ctx):
    out = []
    for i, f in enumerate(spec_features):
        if f["type"] not in REGISTRY:
            raise SystemExit(f"unknown feature type {f['type']!r} (known: {', '.join(sorted(REGISTRY))})")
        out.append(REGISTRY[f["type"]](f, ctx))
    return out


class Feature:
    role = None
    draw_order = 50

    def __init__(self, spec, ctx):
        self.spec = spec
        self.id = spec.get("id", spec["type"])

    def heights(self, ctx):
        return []

    def footprint(self, ctx):
        return None

    def water_fx(self, ctx, img, water):
        return img

    def draw(self, ctx, L):
        pass

    def scene(self, ctx):
        pass


@feature("well")
class Well(Feature):
    """Stone well: mud apron and a moat of deeper water around it, ripples, foam, trinkets.
    spec: at [x, y], r_outer 1.25, r_inner 0.82, state "ooze" (glowing green, light) | "cleared" (still dark water)."""
    role = "focal"
    draw_order = 30

    def __init__(self, spec, ctx):
        super().__init__(spec, ctx)
        self.cx, self.cy = ctx.pt(spec["at"])
        self.ro, self.ri = ctx.px(spec.get("r_outer", 1.25)), ctx.px(spec.get("r_inner", 0.82))
        self.state = spec.get("state", "ooze")
        self.d = np.hypot(ctx.xx - self.cx, ctx.yy - self.cy)

    def heights(self, ctx):
        d, R = self.d, self.ro
        return [(10, lambda h: h + 0.30 * smooth(R + 105, R + 5, d)),                       # mud apron
                (30, lambda h: h - 0.10 * smooth(R + 295, R + 135, d) * smooth(R + 25, R + 135, d))]  # moat

    def footprint(self, ctx):
        return self.d - self.ro

    def water_fx(self, ctx, img, water):
        d, R = self.d, self.ro
        ripple = (0.5 + 0.5 * np.sin(d / 11.0)) * np.exp(-np.maximum(d - R, 0) / 260) * water * smooth(R, R + 20, d)
        img *= (1 + 0.10 * ripple)[..., None]
        if self.state == "ooze":                                     # tint seeping from the well
            img = mix(img, (52, 96, 44), smooth(R + 395, R + 15, d) * water * 0.25)
        return img

    def draw(self, ctx, L):
        R, sd, od = ctx.R, L.sd, L.od
        cx, cy, ro, ri, d = self.cx, self.cy, self.ro, self.ri, self.d
        sd.ellipse([cx - ro + 26, cy - ro + 30, cx + ro + 34, cy + ro + 38], fill=(0, 0, 0, 150))
        for _ in range(220):                                         # foam where it spills over
            a, rr = R.uniform(0, 2 * math.pi), R.uniform(ro + 4, ro + 60)
            fx, fy, fr = cx + rr * math.cos(a), cy + rr * math.sin(a), R.uniform(2, 6)
            od.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=(205, 214, 190, int(R.uniform(60, 150))))
        N = 15
        for i in range(N):                                           # ring stones, lit from the north-west
            a0, a1 = 2 * math.pi * i / N + 0.025, 2 * math.pi * (i + 1) / N - 0.025
            poly = [(cx + (ro + R.uniform(-3, 3)) * math.cos(a), cy + (ro + R.uniform(-3, 3)) * math.sin(a))
                    for a in np.linspace(a0, a1, 6)]
            poly += [(cx + ri * math.cos(a), cy + ri * math.sin(a)) for a in np.linspace(a1, a0, 6)]
            light = 1.0 + 0.18 * math.cos((a0 + a1) / 2 + math.pi * 0.75)
            od.polygon(poly, fill=tuple(int(v * light) for v in vary(R, (106, 104, 94), 8)) + (255,),
                       outline=(58, 56, 50, 255))
            if R.random() < 0.25:
                am = (a0 + a1) / 2 + R.uniform(-0.1, 0.1)
                mx, my = cx + (ri + 14) * math.cos(am), cy + (ri + 14) * math.sin(am)
                od.ellipse([mx - 7, my - 5, mx + 7, my + 5], fill=(58, 82, 42, 170))
        ii = np.zeros((ctx.H, ctx.W, 4))
        t = np.clip(d / ri, 0, 1)
        if self.state == "cleared":                                  # still, dark water, faint reflection
            ii[..., 0] = 12 + 10 * (1 - t)
            ii[..., 1] = 24 + 16 * (1 - t) + 6 * np.sin(d / 6) * (1 - t)
            ii[..., 2] = 26 + 22 * (1 - t)
        else:                                                        # glowing green ooze swirl
            ii[..., 0] = 14 + 58 * (1 - t) ** 2
            ii[..., 1] = 26 + 150 * (1 - t) ** 2 + 18 * np.sin(np.arctan2(ctx.yy - cy, ctx.xx - cx) * 5 + d / 9) * (1 - t)
            ii[..., 2] = 20 + 40 * (1 - t) ** 2
        ii[..., 3] = 255 * (d < ri)
        L.inner.append(Image.fromarray(np.clip(ii, 0, 255).astype(np.uint8), "RGBA"))
        for _ in range(9):                                           # trinkets bobbing near the well
            a, rr = R.uniform(0, 2 * math.pi), R.uniform(ro + 20, ro + 110)
            fx, fy = cx + rr * math.cos(a), cy + rr * math.sin(a)
            od.ellipse([fx - 4, fy - 4, fx + 4, fy + 4], fill=vary(R, (214, 180, 80), 30) + (255,), outline=(60, 50, 30, 255))

    def scene(self, ctx):
        if self.state == "ooze":
            ctx.scene["lights"].append({"at": [round(self.cx), round(self.cy)], "dim": 15, "bright": 5,
                                        "color": "#8fe36a", "alpha": 0.45, "anim": "pulse"})


@feature("causeway")
class Causeway(Feature):
    """Stepping stones along a curve, on a raised bed. spec: path [[x, y], ...] (may start/end off the map),
    spacing 0.58, sunk 0.13 (share of stones missing)."""
    role = "path"
    draw_order = 20

    def __init__(self, spec, ctx):
        super().__init__(spec, ctx)
        self.curve = catmull([ctx.pt(p) for p in spec["path"]])
        self.d = polyline_dist(ctx, self.curve)

    def heights(self, ctx):
        return [(20, lambda h: h + 0.22 * smooth(95, 30, self.d) * (0.7 + 0.3 * fbm(ctx, [(20, 1)])))]

    def footprint(self, ctx):
        return self.d

    def draw(self, ctx, L):
        R, sd, od, path = ctx.R, L.sd, L.od, self.curve
        spacing, sunk = ctx.px(self.spec.get("spacing", 0.58)), self.spec.get("sunk", 0.13)
        s = 0
        for i in range(1, len(path)):
            s += float(np.hypot(*(path[i] - path[i - 1])))
            if s < spacing:
                continue
            s = 0
            if R.random() < sunk:
                continue
            x, y = path[i] + R.normal(0, 7, 2)
            poly = jitter_poly(R, x, y, R.uniform(22, 32), int(R.integers(6, 9)), 0.22, R.uniform(0, 6.3))
            sd.polygon([(px + 6, py + 7) for px, py in poly], fill=(0, 0, 0, 120))
            od.polygon(poly, fill=vary(R, (116, 117, 104), 12) + (255,), outline=(70, 70, 62, 255))
            od.polygon([(x + (px - x) * .55 - 4, y + (py - y) * .55 - 4) for px, py in poly], fill=vary(R, (140, 140, 126), 8) + (120,))
            if R.random() < 0.45:
                mx, my = poly[R.integers(len(poly))]
                od.ellipse([mx - 9, my - 7, mx + 9, my + 7], fill=(78, 104, 52, 200))


@feature("hummock")
class Hummock(Feature):
    """A rise of firm ground: footing and cover. spec: at [x, y], r (squares)."""

    def __init__(self, spec, ctx):
        super().__init__(spec, ctx)
        x, y = ctx.pt(spec["at"])
        self.r = ctx.px(spec["r"])
        self.d = np.hypot(ctx.xx - x, ctx.yy - y)

    def heights(self, ctx):
        return [(50, lambda h: h + 0.24 * smooth(self.r, self.r * 0.45, self.d) * (0.75 + 0.25 * fbm(ctx, [(18, 1)])))]


@feature("trees")
class Trees(Feature):
    """A stand of trees: root tangles under blurred canopies. Best placed on or past the map edge.
    spec: at [[x, y], ...], kind "mangrove"."""
    draw_order = 10

    def __init__(self, spec, ctx):
        super().__init__(spec, ctx)
        self.at = [ctx.pt(p) for p in spec["at"]]

    def draw(self, ctx, L):
        R = ctx.R
        for tx, ty in self.at:
            for _ in range(R.integers(12, 18)):
                a = R.uniform(0, 2 * math.pi)
                x, y, w = tx, ty, R.uniform(7, 11)
                pts = [(x, y)]
                for _ in range(R.integers(6, 11)):
                    a += R.uniform(-0.45, 0.45)
                    step = R.uniform(18, 30)
                    x, y = x + step * math.cos(a), y + step * math.sin(a)
                    pts.append((x, y))
                for i in range(len(pts) - 1):
                    ww = max(2, int(w * (1 - i / len(pts))))
                    L.sd.line([(pts[i][0] + 5, pts[i][1] + 6), (pts[i + 1][0] + 5, pts[i + 1][1] + 6)], fill=(0, 0, 0, 120), width=ww + 2)
                    L.od.line([pts[i], pts[i + 1]], fill=vary(R, (62, 47, 31), 8) + (255,), width=ww)
        for tx, ty in self.at:
            for _ in range(R.integers(14, 24)):
                r = R.uniform(40, 95)
                cx, cy = tx + R.normal(0, 70), ty + R.normal(0, 70)
                L.csd.ellipse([cx - r + 30, cy - r + 34, cx + r + 30, cy + r + 34], fill=(0, 0, 0, 140))
                L.cd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=vary(R, (38, 60, 32), 9) + (255,))
                r2 = r * 0.55
                L.cd.ellipse([cx - r2 - r * .25, cy - r2 - r * .25, cx + r2 - r * .25, cy + r2 - r * .25], fill=vary(R, (58, 86, 44), 10) + (150,))
