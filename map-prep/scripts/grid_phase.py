#!/usr/bin/env python3
"""Measure the grid pitch and phase (offset of the first grid line) of a battle-map image.

  grid_phase.py map.png [--min 40 --max 300] [--box x0,y0,x1,y1]

Prints JSON: {"pitch_x":..., "pitch_y":..., "phase_x":..., "phase_y":..., "score_x":..., "score_y":...}
Grid lines sit at x = phase_x + k*pitch_x (sub-pixel). Use --box to restrict to a region that
actually has a grid (e.g. one floor on a book page with margins and text).

Method: per-column / per-row gradient energy -> high-pass -> autocorrelation gives the pitch
(smallest strong peak, to avoid harmonics) -> fine comb search refines pitch to 0.02px and finds
the phase. Never eyeball this. A crop that was "close" once had the grid off by ~40px (0.4 square).
"""
import argparse, json
import numpy as np
from PIL import Image


def profile(gray, axis):
    g = np.abs(np.diff(gray, axis=1 - axis))       # axis=0 -> vertical lines -> diff along x
    p = g.mean(axis=0 if axis == 0 else 1)
    k = 61
    hp = p - np.convolve(p, np.ones(k) / k, mode="same")
    return np.clip(hp, 0, None)


def pitch_phase(p, lo, hi):
    n = len(p)
    f = np.fft.rfft(p - p.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac /= ac[0] + 1e-9
    hi = min(hi, n // 2)
    seg = ac[lo:hi]
    peaks = [i for i in range(1, len(seg) - 1) if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1]]
    if not peaks:
        raise SystemExit("no periodicity found")
    best = max(seg[i] for i in peaks)
    lag = lo + min(i for i in peaks if seg[i] >= 0.8 * best)
    x = np.arange(n)
    best_s, best_p, best_ph = -1, None, None
    for pitch in np.arange(lag - 2, lag + 2, 0.02):
        k = np.arange(0, int(n / pitch))
        for ph in np.arange(0, pitch, 0.5):
            idx = np.round(ph + k * pitch).astype(int)
            idx = idx[idx < n]
            s = p[idx].mean()
            if s > best_s:
                best_s, best_p, best_ph = s, pitch, ph
    return float(best_p), float(best_ph), float(best_s / (p.mean() + 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--min", type=int, default=40)
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--box", help="x0,y0,x1,y1 region to analyse (phase reported in full-image coords)")
    a = ap.parse_args()
    im = Image.open(a.image).convert("L")
    ox = oy = 0
    if a.box:
        ox, oy, x1, y1 = map(int, a.box.split(","))
        im = im.crop((ox, oy, x1, y1))
    gray = np.asarray(im, float)
    px, phx, sx = pitch_phase(profile(gray, 0), a.min, a.max)
    py, phy, sy = pitch_phase(profile(gray, 1), a.min, a.max)
    # diff shifts edges by half a pixel; lines are ~1-2px, report the line centre
    phx = (phx + ox + 0.5) % px
    phy = (phy + oy + 0.5) % py
    print(json.dumps({"pitch_x": round(px, 2), "pitch_y": round(py, 2), "phase_x": round(phx, 1),
                      "phase_y": round(phy, 1), "score_x": round(sx, 2), "score_y": round(sy, 2)}))


if __name__ == "__main__":
    main()
