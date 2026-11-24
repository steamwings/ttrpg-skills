"""Swamp: open water, mud, moss, reeds on the shallows, lily pads in open water.

Height field: water < 0.52 < mud < 0.62 < moss. Features raise or lower it (see features.py);
reeds and lilies stay clear of "focal" features (wells) and "path" features (causeways).
"""
import math

import numpy as np

from ..core import fbm, fog, hillshade, mix, smooth, to_image, vary

DEEP, SHALLOW, MUD, MOSS, MOSS_L = (30, 43, 34), (60, 73, 49), (94, 77, 52), (70, 90, 47), (99, 117, 62)


def _clear(ctx, feats, role):
    fields = [f.footprint(ctx) for f in feats if f.role == role]
    return np.minimum.reduce(fields) if fields else np.full((ctx.H, ctx.W), np.inf)


def render(ctx, feats):
    W, H = ctx.W, ctx.H
    dfocal, dpath = _clear(ctx, feats, "focal"), _clear(ctx, feats, "path")

    # --- height field --------------------------------------------------------------------------
    h = fbm(ctx, [(140, 1.0), (70, 0.55), (30, 0.3), (12, 0.14), (4, 0.06)])
    h = 0.15 + 0.7 * h
    terms = [(40, lambda h: h + 0.10 * smooth(260, 40, ctx.edge))]          # firmer ground under the edge trees
    terms += [t for f in feats for t in f.heights(ctx)]
    for _, fn in sorted(terms, key=lambda t: t[0]):
        h = fn(h)
    h = np.clip(h, 0, 1)

    # --- colour --------------------------------------------------------------------------------
    img = np.zeros((H, W, 3))
    img[:] = DEEP
    img = mix(img, SHALLOW, smooth(0.40, 0.52, h))
    img = mix(img, MUD, smooth(0.52, 0.56, h))
    img = mix(img, MOSS, smooth(0.62, 0.70, h) * (0.6 + 0.4 * fbm(ctx, [(25, 1), (8, .5)])))
    img = mix(img, MOSS_L, smooth(0.72, 0.80, h) * 0.6)
    land = smooth(0.52, 0.56, h)
    water = 1 - land
    img *= (1 + (hillshade(h) - 1) * land)[..., None]
    img *= (1 - 0.22 * np.exp(-((h - 0.53) / 0.012) ** 2))[..., None]      # wet band at the waterline
    scum = smooth(0.70, 0.80, fbm(ctx, [(14, 1), (5, .4)])) * water * smooth(35, 135, dfocal)
    img = mix(img, (78, 96, 48), scum * 0.35)
    for f in feats:
        img = f.water_fx(ctx, img, water)
    img += ctx.noise.normal(0, 3.0, img.shape)
    base = to_image(img)

    # --- reeds on shallow edges, lily pads in open water ----------------------------------------
    R, L = ctx.R, ctx.layers
    cand = np.argwhere((h > 0.47) & (h < 0.53) & (dfocal > 95) & (dpath > 60))
    for y, x in cand[R.choice(len(cand), min(len(cand), ctx.scale(260)), replace=False)]:
        for _ in range(R.integers(5, 10)):
            a, ln = R.uniform(0, 2 * math.pi), R.uniform(10, 28)
            x2, y2 = x + ln * math.cos(a), y + ln * math.sin(a)
            L.od.line([(x, y), (x2, y2)], fill=vary(R, (52, 66, 30), 10) + (235,), width=2)
            L.od.ellipse([x2 - 2, y2 - 2, x2 + 2, y2 + 2], fill=(118, 96, 58, 230))
    cand = np.argwhere((h < 0.47) & (dfocal > 135) & (dpath > 70) & (ctx.edge > 120))
    for y, x in cand[R.choice(len(cand), min(len(cand), ctx.scale(140)), replace=False)]:
        r, a0 = R.uniform(7, 15), R.uniform(0, 360)
        L.sd.ellipse([x - r + 3, y - r + 3, x + r + 3, y + r + 3], fill=(0, 0, 0, 70))
        L.od.pieslice([x - r, y - r, x + r, y + r], a0 + 25, a0 + 360, fill=vary(R, (66, 108, 50), 14) + (255,), outline=(40, 70, 34, 255))
        if R.random() < 0.12:
            L.od.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(236, 214, 226, 255))

    # --- features, then fog --------------------------------------------------------------------
    for f in sorted(feats, key=lambda f: f.draw_order):
        f.draw(ctx, L)
    for f in feats:
        f.scene(ctx)
    return fog(ctx, L.composite(base), ctx.spec.get("fog"))
