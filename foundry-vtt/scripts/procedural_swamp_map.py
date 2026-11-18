"""Procedural top-down swamp battle map: open water, mud hummocks, a stepping-stone causeway,
mangroves and edge fog around a central stone well. No source art needed.

20 x 14 squares at 100 px (5 ft), grid phase 0 (Foundry draws the grid; none is baked in).
Writes OUT (webp) and OUT-preview.jpg (half size, with a grid, for checking by eye).

Usage: python3 procedural_swamp_map.py OUT.webp [seed] [cleared]
  seed     fixed seed -> identical map on every run (default 7)
  cleared  the well holds still dark water instead of a glowing green ooze

Tweak WELL, PATH (causeway control points) and HUMMOCKS to change the layout.
Needs numpy, scipy, pillow. About 15 s.
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt, gaussian_filter

OUT = sys.argv[1]
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 7
CLEARED = len(sys.argv) > 3 and sys.argv[3] == "cleared"
W, H, G = 2000, 1400, 100
WELL = (1050, 640)          # well centre (px)
R_OUT, R_IN = 125, 82       # stone ring radii
PATH = [(-60, 1010), (300, 950), (650, 890), (980, 860), (1300, 800), (1600, 700), (1850, 600), (2060, 540)]
HUMMOCKS = [(430, 380, 150), (1480, 340, 120), (1520, 1060, 160), (640, 1170, 120), (260, 760, 100)]  # x, y, radius
TREES = [(80, 90), (330, -20), (-30, 420), (1500, -40), (1880, 80), (2040, 380), (1950, 1300),
         (1620, 1440), (200, 1350), (-40, 1150), (760, 1460), (1180, 1440), (900, -60)]
rng = np.random.default_rng(SEED)


def fbm(octaves):
    acc = np.zeros((H, W))
    for sigma, weight in octaves:
        n = gaussian_filter(rng.standard_normal((H, W)), sigma, mode="reflect")
        acc += weight * n / (n.std() + 1e-9)
    acc -= acc.min()
    return acc / acc.max()


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a * (1 - t[..., None]) + np.asarray(b, float) * t[..., None]


def catmull(points, n=40):
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = map(np.array, pts[i - 1:i + 3])
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


yy, xx = np.mgrid[0:H, 0:W]
dwell = np.hypot(xx - WELL[0], yy - WELL[1])
path = catmull(PATH)
pmask = Image.new("L", (W, H), 255)
ImageDraw.Draw(pmask).line([tuple(p) for p in path], fill=0, width=3)
dpath = distance_transform_edt(np.array(pmask) > 0)
edge = np.minimum.reduce([xx, yy, W - 1 - xx, H - 1 - yy])

# --- height field: water < 0.52 < mud < 0.62 < moss ---------------------------
h = fbm([(140, 1.0), (70, 0.55), (30, 0.3), (12, 0.14), (4, 0.06)])
h = 0.15 + 0.7 * h
h += 0.30 * smooth(230, 130, dwell)                                # mud apron around the well
h += 0.22 * smooth(95, 30, dpath) * (0.7 + 0.3 * fbm([(20, 1)]))   # raised causeway bed
h -= 0.10 * smooth(420, 260, dwell) * smooth(150, 260, dwell)      # moat of deeper water
h += 0.10 * smooth(260, 40, edge)                                  # firmer ground under the edge trees
for hx, hy, hr in HUMMOCKS:                                        # footing and cover away from the well
    h += 0.24 * smooth(hr, hr * 0.45, np.hypot(xx - hx, yy - hy)) * (0.75 + 0.25 * fbm([(18, 1)]))
h = np.clip(h, 0, 1)

DEEP, SHALLOW, MUD, MOSS, MOSS_L = (30, 43, 34), (60, 73, 49), (94, 77, 52), (70, 90, 47), (99, 117, 62)
img = np.zeros((H, W, 3))
img[:] = DEEP
img = mix(img, SHALLOW, smooth(0.40, 0.52, h))
img = mix(img, MUD, smooth(0.52, 0.56, h))
img = mix(img, MOSS, smooth(0.62, 0.70, h) * (0.6 + 0.4 * fbm([(25, 1), (8, .5)])))
img = mix(img, MOSS_L, smooth(0.72, 0.80, h) * 0.6)
land = smooth(0.52, 0.56, h)
water = 1 - land

hs = gaussian_filter(h, 3)                                         # hillshade on land
gy, gx = np.gradient(hs)
shade = np.clip(1 + 55 * (-gx - gy), 0.75, 1.25)
img *= (1 + (shade - 1) * land)[..., None]
img *= (1 - 0.22 * np.exp(-((h - 0.53) / 0.012) ** 2))[..., None]   # wet band at the waterline

scum = smooth(0.70, 0.80, fbm([(14, 1), (5, .4)])) * water * smooth(160, 260, dwell)
img = mix(img, (78, 96, 48), scum * 0.35)
ripple = (0.5 + 0.5 * np.sin(dwell / 11.0)) * np.exp(-np.maximum(dwell - R_OUT, 0) / 260) * water * smooth(R_OUT, R_OUT + 20, dwell)
img *= (1 + 0.10 * ripple)[..., None]
if not CLEARED:                                                    # ooze tint seeping from the well
    img = mix(img, (52, 96, 44), smooth(520, 140, dwell) * water * 0.25)
img += rng.normal(0, 3.0, img.shape)
base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
sd, od = ImageDraw.Draw(shadow), ImageDraw.Draw(over)
R = np.random.default_rng(SEED + 1)


def jitter_poly(cx, cy, r, n, j=0.25, rot=0.0):
    pts = []
    for i in range(n):
        a = rot + 2 * math.pi * i / n + R.uniform(-0.15, 0.15)
        rr = r * (1 + R.uniform(-j, j))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def vary(c, amt=12):
    return tuple(int(np.clip(v + R.integers(-amt, amt + 1), 0, 255)) for v in c)


# --- reeds on shallow edges, lily pads in open water --------------------------
cand = np.argwhere((h > 0.47) & (h < 0.53) & (dwell > 220) & (dpath > 60))
for y, x in cand[R.choice(len(cand), 260, replace=False)]:
    for _ in range(R.integers(5, 10)):
        a, ln = R.uniform(0, 2 * math.pi), R.uniform(10, 28)
        x2, y2 = x + ln * math.cos(a), y + ln * math.sin(a)
        od.line([(x, y), (x2, y2)], fill=vary((52, 66, 30), 10) + (235,), width=2)
        od.ellipse([x2 - 2, y2 - 2, x2 + 2, y2 + 2], fill=(118, 96, 58, 230))
cand = np.argwhere((h < 0.47) & (dwell > 260) & (dpath > 70) & (edge > 120))
for y, x in cand[R.choice(len(cand), 140, replace=False)]:
    r, a0 = R.uniform(7, 15), R.uniform(0, 360)
    sd.ellipse([x - r + 3, y - r + 3, x + r + 3, y + r + 3], fill=(0, 0, 0, 70))
    od.pieslice([x - r, y - r, x + r, y + r], a0 + 25, a0 + 360, fill=vary((66, 108, 50), 14) + (255,), outline=(40, 70, 34, 255))
    if R.random() < 0.12:
        od.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(236, 214, 226, 255))

# --- mangroves: root tangles and canopies, mostly off the edges ---------------
for tx, ty in TREES:
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
            sd.line([(pts[i][0] + 5, pts[i][1] + 6), (pts[i + 1][0] + 5, pts[i + 1][1] + 6)], fill=(0, 0, 0, 120), width=ww + 2)
            od.line([pts[i], pts[i + 1]], fill=vary((62, 47, 31), 8) + (255,), width=ww)
canopy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cshadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cd, csd = ImageDraw.Draw(canopy), ImageDraw.Draw(cshadow)
for tx, ty in TREES:
    for _ in range(R.integers(14, 24)):
        r = R.uniform(40, 95)
        cx, cy = tx + R.normal(0, 70), ty + R.normal(0, 70)
        csd.ellipse([cx - r + 30, cy - r + 34, cx + r + 30, cy + r + 34], fill=(0, 0, 0, 140))
        cd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=vary((38, 60, 32), 9) + (255,))
        r2 = r * 0.55
        cd.ellipse([cx - r2 - r * .25, cy - r2 - r * .25, cx + r2 - r * .25, cy + r2 - r * .25], fill=vary((58, 86, 44), 10) + (150,))

# --- causeway stepping stones (a few have sunk) ------------------------------
s = 0
for i in range(1, len(path)):
    s += float(np.hypot(*(path[i] - path[i - 1])))
    if s < 58:
        continue
    s = 0
    if R.random() < 0.13:
        continue
    x, y = path[i] + R.normal(0, 7, 2)
    poly = jitter_poly(x, y, R.uniform(22, 32), int(R.integers(6, 9)), 0.22, R.uniform(0, 6.3))
    sd.polygon([(px + 6, py + 7) for px, py in poly], fill=(0, 0, 0, 120))
    od.polygon(poly, fill=vary((116, 117, 104), 12) + (255,), outline=(70, 70, 62, 255))
    od.polygon([(x + (px - x) * .55 - 4, y + (py - y) * .55 - 4) for px, py in poly], fill=vary((140, 140, 126), 8) + (120,))
    if R.random() < 0.45:
        mx, my = poly[R.integers(len(poly))]
        od.ellipse([mx - 9, my - 7, mx + 9, my + 7], fill=(78, 104, 52, 200))

# --- the well -------------------------------------------------------------------
cx, cy = WELL
sd.ellipse([cx - R_OUT + 26, cy - R_OUT + 30, cx + R_OUT + 34, cy + R_OUT + 38], fill=(0, 0, 0, 150))
for _ in range(220):                                               # foam where it spills over
    a, rr = R.uniform(0, 2 * math.pi), R.uniform(R_OUT + 4, R_OUT + 60)
    fx, fy, fr = cx + rr * math.cos(a), cy + rr * math.sin(a), R.uniform(2, 6)
    od.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=(205, 214, 190, int(R.uniform(60, 150))))
N = 15
for i in range(N):
    a0, a1 = 2 * math.pi * i / N + 0.025, 2 * math.pi * (i + 1) / N - 0.025
    poly = [(cx + (R_OUT + R.uniform(-3, 3)) * math.cos(a), cy + (R_OUT + R.uniform(-3, 3)) * math.sin(a)) for a in np.linspace(a0, a1, 6)]
    poly += [(cx + R_IN * math.cos(a), cy + R_IN * math.sin(a)) for a in np.linspace(a1, a0, 6)]
    light = 1.0 + 0.18 * math.cos((a0 + a1) / 2 + math.pi * 0.75)   # lit from the north-west
    od.polygon(poly, fill=tuple(int(v * light) for v in vary((106, 104, 94), 8)) + (255,), outline=(58, 56, 50, 255))
    if R.random() < 0.25:
        am = (a0 + a1) / 2 + R.uniform(-0.1, 0.1)
        mx, my = cx + (R_IN + 14) * math.cos(am), cy + (R_IN + 14) * math.sin(am)
        od.ellipse([mx - 7, my - 5, mx + 7, my + 5], fill=(58, 82, 42, 170))
ii = np.zeros((H, W, 4))
t = np.clip(dwell / R_IN, 0, 1)
if CLEARED:   # still, dark water with a faint reflection
    ii[..., 0] = 12 + 10 * (1 - t)
    ii[..., 1] = 24 + 16 * (1 - t) + 6 * np.sin(dwell / 6) * (1 - t)
    ii[..., 2] = 26 + 22 * (1 - t)
else:         # glowing green ooze swirl
    ii[..., 0] = 14 + 58 * (1 - t) ** 2
    ii[..., 1] = 26 + 150 * (1 - t) ** 2 + 18 * np.sin(np.arctan2(yy - cy, xx - cx) * 5 + dwell / 9) * (1 - t)
    ii[..., 2] = 20 + 40 * (1 - t) ** 2
ii[..., 3] = 255 * (dwell < R_IN)
inner = Image.fromarray(np.clip(ii, 0, 255).astype(np.uint8), "RGBA")
for _ in range(9):                                                 # trinkets bobbing near the well
    a, rr = R.uniform(0, 2 * math.pi), R.uniform(R_OUT + 20, R_OUT + 110)
    fx, fy = cx + rr * math.cos(a), cy + rr * math.sin(a)
    od.ellipse([fx - 4, fy - 4, fx + 4, fy + 4], fill=vary((214, 180, 80), 30) + (255,), outline=(60, 50, 30, 255))

# --- composite, then fog at the edges and a few drifting patches ---------------
out = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(6)))
out = Image.alpha_composite(out, over)
out = Image.alpha_composite(out, inner)
out = Image.alpha_composite(out, cshadow.filter(ImageFilter.GaussianBlur(18)))
out = Image.alpha_composite(out, canopy.filter(ImageFilter.GaussianBlur(1.2)))
fog = smooth(200, 0, edge) * (0.45 + 0.55 * fbm([(40, 1), (15, .4)]))
fog = np.maximum(fog * 0.42, 0.10 * smooth(0.70, 0.86, fbm([(60, 1), (25, .5)])))
fa = np.zeros((H, W, 4))
fa[..., :3] = (196, 204, 192)
fa[..., 3] = 255 * fog
out = Image.alpha_composite(out, Image.fromarray(fa.astype(np.uint8), "RGBA")).convert("RGB")
out.save(OUT, "WEBP", quality=86, method=6)

prev = out.resize((W // 2, H // 2), Image.LANCZOS)
d = ImageDraw.Draw(prev)
for gx in range(0, W // 2, G // 2):
    d.line([(gx, 0), (gx, H // 2)], fill=(0, 0, 0), width=1)
for gy in range(0, H // 2, G // 2):
    d.line([(0, gy), (W // 2, gy)], fill=(0, 0, 0), width=1)
prev.save(OUT.rsplit(".", 1)[0] + "-preview.jpg", quality=85)
print("wrote", OUT)
