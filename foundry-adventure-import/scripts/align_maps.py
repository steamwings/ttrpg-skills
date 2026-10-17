#!/usr/bin/env python3
"""align_maps.py BOOK_MAP LEVEL_IMG [LEVEL_IMG ...] — find where each scene image sits in the book map.

Prints, per level image, a similarity transform book->level (scale, rotation, tx, ty) from SIFT matches + RANSAC,
with the inlier count. Use it to carry 5etools `mapRegions` polygons (book-map pixels) onto scene images.
Output JSON on stdout: {level_img: {"M": 2x3 matrix book->level, "inliers": n, "scale": s, "rot_deg": r}}.
"""
import json, math, sys
import cv2
import numpy as np


def load(path, max_side=2400):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im.ndim == 3 and im.shape[2] == 4:   # transparent background -> white
        a = im[:, :, 3:4] / 255.0
        im = (im[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    f = min(1.0, max_side / max(g.shape))
    return cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA), f


def main(book, *levels):
    sift = cv2.SIFT_create(nfeatures=20000)
    bg, bf = load(book)
    kb, db = sift.detectAndCompute(bg, None)
    out = {}
    for lv in levels:
        lg, lf = load(lv)
        kl, dl = sift.detectAndCompute(lg, None)
        m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(db, dl, k=2)
        good = [a for a, b in m if a.distance < 0.75 * b.distance]
        src = np.float32([kb[g.queryIdx].pt for g in good]) / bf
        dst = np.float32([kl[g.trainIdx].pt for g in good]) / lf
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
        n = int(inl.sum()) if inl is not None else 0
        s = math.hypot(M[0, 0], M[1, 0]) if M is not None else 0
        out[lv] = {"M": M.tolist() if M is not None else None, "inliers": n, "matches": len(good),
                   "scale": round(s, 4), "rot_deg": round(math.degrees(math.atan2(M[1, 0], M[0, 0])), 2) if M is not None else None}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
