"""Shared toolkit for procedural battle maps: canvas, noise, shapes, layer stack, fog, output.

Units: specs use grid squares; everything in here works in image pixels (ctx.px converts).
Two random streams keep maps reproducible from a seed:
  ctx.noise  terrain noise (fbm), consumed in a fixed order by the biome
  ctx.R      decoration (reeds, stones, trees...), consumed in draw order
Adding a draw call early in the order changes everything drawn after it, so new decoration
goes after the existing calls or behind a spec option.
"""
import json
import math
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt, gaussian_filter


class Layers:
    """The standard stack, bottom to top: base terrain, ground shadows (blurred), ground overlay,
    insets (well water, pools), canopy shadows (blurred more), canopy, then fog (core.fog)."""

    def __init__(self, W, H):
        new = lambda: Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.shadow, self.over, self.cshadow, self.canopy = new(), new(), new(), new()
        self.sd, self.od = ImageDraw.Draw(self.shadow), ImageDraw.Draw(self.over)
        self.csd, self.cd = ImageDraw.Draw(self.cshadow), ImageDraw.Draw(self.canopy)
        self.inner = []   # full-size RGBA images

    def composite(self, base):
        out = Image.alpha_composite(base, self.shadow.filter(ImageFilter.GaussianBlur(6)))
        out = Image.alpha_composite(out, self.over)
        for im in self.inner:
            out = Image.alpha_composite(out, im)
        out = Image.alpha_composite(out, self.cshadow.filter(ImageFilter.GaussianBlur(18)))
        return Image.alpha_composite(out, self.canopy.filter(ImageFilter.GaussianBlur(1.2)))


class Ctx:
    def __init__(self, spec, seed):
        self.spec = spec
        self.G = spec.get("grid", {}).get("size", 100)
        cols, rows = spec["size"]
        self.W, self.H = int(round(cols * self.G)), int(round(rows * self.G))
        self.seed = seed
        self.noise = np.random.default_rng(seed)
        self.R = np.random.default_rng(seed + 1)
        self.yy, self.xx = np.mgrid[0:self.H, 0:self.W]
        self.edge = np.minimum.reduce([self.xx, self.yy, self.W - 1 - self.xx, self.H - 1 - self.yy])
        self.layers = Layers(self.W, self.H)
        self.scene = {"walls": [], "interiors": [], "lights": []}

    def px(self, v):
        """Squares -> pixels (rounded so 0.6 squares is exactly 60 px)."""
        return round(v * self.G, 6)

    def pt(self, p):
        return (self.px(p[0]), self.px(p[1]))

    def scale(self, n):
        """Scale a decoration count tuned for a 20x14 map to this map's area."""
        return int(round(n * self.W * self.H / (2000 * 1400)))


# --- noise and shaping --------------------------------------------------------------------------

def fbm(ctx, octaves):
    """Fractal noise in [0, 1]: a sum of blurred white noise, octaves = [(sigma_px, weight), ...]."""
    acc = np.zeros((ctx.H, ctx.W))
    for sigma, weight in octaves:
        n = gaussian_filter(ctx.noise.standard_normal((ctx.H, ctx.W)), sigma, mode="reflect")
        acc += weight * n / (n.std() + 1e-9)
    acc -= acc.min()
    return acc / acc.max()


def smooth(e0, e1, x):
    """Smoothstep from e0 to e1 (e0 > e1 gives a falling edge)."""
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a * (1 - t[..., None]) + np.asarray(b, float) * t[..., None]


def catmull(points, n=40):
    """Catmull-Rom curve through the control points (ends repeated)."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = map(np.array, pts[i - 1:i + 3])
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


def polyline_dist(ctx, curve):
    """Distance in px from every pixel to a polyline."""
    mask = Image.new("L", (ctx.W, ctx.H), 255)
    ImageDraw.Draw(mask).line([tuple(p) for p in curve], fill=0, width=3)
    return distance_transform_edt(np.array(mask) > 0)


def jitter_poly(R, cx, cy, r, n, j=0.25, rot=0.0):
    pts = []
    for i in range(n):
        a = rot + 2 * math.pi * i / n + R.uniform(-0.15, 0.15)
        rr = r * (1 + R.uniform(-j, j))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def vary(R, c, amt=12):
    return tuple(int(np.clip(v + R.integers(-amt, amt + 1), 0, 255)) for v in c)


def hillshade(h, sigma=3, gain=55, lo=0.75, hi=1.25):
    """Light from the north-west; returns a multiplier field."""
    gy, gx = np.gradient(gaussian_filter(h, sigma))
    return np.clip(1 + gain * (-gx - gy), lo, hi)


# --- finishing ----------------------------------------------------------------------------------

FOG_DEFAULT = {"edge": 2.0, "strength": 0.42, "patches": 0.10, "color": [196, 204, 192]}


def fog(ctx, img, opts):
    """Edge fog plus drifting patches. opts: false, or overrides of FOG_DEFAULT (edge in squares)."""
    if opts is False:
        return img
    o = {**FOG_DEFAULT, **(opts or {})}
    f = smooth(ctx.px(o["edge"]), 0, ctx.edge) * (0.45 + 0.55 * fbm(ctx, [(40, 1), (15, .4)]))
    f = np.maximum(f * o["strength"], o["patches"] * smooth(0.70, 0.86, fbm(ctx, [(60, 1), (25, .5)])))
    fa = np.zeros((ctx.H, ctx.W, 4))
    fa[..., :3] = o["color"]
    fa[..., 3] = 255 * f
    return Image.alpha_composite(img, Image.fromarray(fa.astype(np.uint8), "RGBA"))


def to_image(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def save(ctx, img, out_path):
    """Map as webp (no grid baked in) and a half-size preview with the grid drawn, for checking."""
    img = img.convert("RGB")
    img.save(out_path, "WEBP", quality=86, method=6)
    W, H, G = ctx.W, ctx.H, ctx.G
    prev = img.resize((W // 2, H // 2), Image.LANCZOS)
    d = ImageDraw.Draw(prev)
    for gx in range(0, W // 2, G // 2):
        d.line([(gx, 0), (gx, H // 2)], fill=(0, 0, 0), width=1)
    for gy in range(0, H // 2, G // 2):
        d.line([(0, gy), (W // 2, gy)], fill=(0, 0, 0), width=1)
    prev_path = str(out_path).rsplit(".", 1)[0] + "-preview.jpg"
    prev.save(prev_path, quality=85)
    return prev_path


def write_scene(ctx, out_dir, image_name):
    """scene.json in the format foundry-adventure-import/scripts/build-scene.js reads (image px)."""
    s = ctx.spec
    scene = {"name": s["name"], "image": image_name, "src": s.get("src", f"assets/maps/{image_name}"),
             "width": ctx.W, "height": ctx.H,
             "grid": {"size": ctx.G, "distance": s.get("grid", {}).get("distance", 5)},
             "darkness": s.get("darkness", 0.3), "global": s.get("global", True), **ctx.scene}
    for k in ("folder", "journal", "page"):
        if k in s:
            scene[k] = s[k]
    path = pathlib.Path(out_dir) / "scene.json"
    path.write_text(json.dumps(scene, indent=1))
    return path
