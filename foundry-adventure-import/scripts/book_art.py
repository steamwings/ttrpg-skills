#!/usr/bin/env python3
"""book_art.py MAP.json CROPS.json WORK_DIR [--base URL] — official art for actors: portraits + round tokens.

MAP:   {"Actor name": "image path under the 5etools-img repo"}, e.g. a bestiary fluff image
       ("bestiary/<SRC>/<Name>.webp") or a book illustration ("adventure/<SRC>/<file>.webp").
CROPS: {"Actor name": [cx, cy, size]} — only for actors that need a new token (no official token, or the current one
       is generic): crop centre as fractions of width/height, square side as a fraction of the width.
Writes WORK_DIR/src (downloads), WORK_DIR/out (portraits/<slug>.webp max 1400px, tokens/token-<slug>.webp 400px,
round, gold rim), WORK_DIR/out/plan.json {name: {img: "portraits/x.webp", token?: "tokens/y.webp"}} for apply-art.js,
and WORK_DIR/tokens-preview.jpg to eyeball the crops (faces centred?) before uploading.
"""
import json, os, re, subprocess, sys, urllib.parse
from PIL import Image, ImageDraw

args = sys.argv[1:]
base = "https://raw.githubusercontent.com/5etools-mirror-3/5etools-img/main"
if "--base" in args:
    i = args.index("--base"); base = args[i + 1]; del args[i:i + 2]
map_f, crops_f, work = args
art, crops = json.load(open(map_f)), json.load(open(crops_f))
os.makedirs(f"{work}/src", exist_ok=True); os.makedirs(f"{work}/out", exist_ok=True)
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

plan = {}
for name, path in art.items():
    src = f"{work}/src/" + path.replace("/", "__")
    if not os.path.exists(src):
        r = subprocess.run(["curl", "-s", "-o", src, "-w", "%{http_code}", f"{base}/{urllib.parse.quote(path)}"],
                           capture_output=True, text=True)
        if r.stdout != "200":
            os.remove(src); print(f"skip {name}: HTTP {r.stdout} for {path}"); continue
    im = Image.open(src)
    pn = slug(os.path.basename(path).rsplit(".", 1)[0]) + ".webp"
    if not os.path.exists(f"{work}/out/{pn}"):
        q = im.copy(); q.thumbnail((1400, 1400)); q.save(f"{work}/out/{pn}", quality=85)
    e = {"img": f"portraits/{pn}"}
    if name in crops:
        cx, cy, s = crops[name]; W, H = im.size; S = s * W
        x0, y0 = max(0, min(W - S, cx * W - S / 2)), max(0, min(H - S, cy * H - S / 2))
        t = im.convert("RGBA").crop((int(x0), int(y0), int(x0 + S), int(y0 + S))).resize((400, 400), Image.LANCZOS)
        mask = Image.new("L", (400, 400), 0); ImageDraw.Draw(mask).ellipse((4, 4, 396, 396), fill=255)
        bg = Image.new("RGBA", (400, 400), (30, 24, 40, 255)); bg.alpha_composite(t)   # art with transparency
        tok = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); tok.paste(bg, (0, 0), mask)
        ImageDraw.Draw(tok).ellipse((4, 4, 396, 396), outline=(200, 160, 60, 255), width=10)
        tn = f"token-{slug(name)}.webp"; tok.save(f"{work}/out/{tn}", quality=90); e["token"] = f"tokens/{tn}"
    plan[name] = e
json.dump(plan, open(f"{work}/out/plan.json", "w"), indent=1)

ts = sorted(f for f in os.listdir(f"{work}/out") if f.startswith("token-"))
if ts:
    sh = Image.new("RGBA", (200 * 6, 200 * ((len(ts) + 5) // 6)), "white")
    for i, f in enumerate(ts):
        sh.alpha_composite(Image.open(f"{work}/out/{f}").resize((200, 200)), ((i % 6) * 200, (i // 6) * 200))
    sh.convert("RGB").save(f"{work}/tokens-preview.jpg")
print(f"{len(plan)} actors, {len(ts)} tokens -> {work}/out/plan.json")
