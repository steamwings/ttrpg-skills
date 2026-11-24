#!/usr/bin/env python3
"""generate_map.py SPEC.json OUT_DIR [--seed N] [--set ID.KEY=VALUE ...]

Renders a grid-aligned battle map from a layout spec (see ../SKILL.md and ../examples/) and writes to OUT_DIR:
  <file>.webp           the map, grid phase 0, no grid baked in (Foundry draws it)
  <file>-preview.jpg    half size with the grid drawn, to check by eye
  scene.json            name, size, grid, darkness, walls, lights, interiors for
                        foundry-adventure-import/scripts/build-scene.js

--seed overrides the spec's seed. --set changes one feature field without editing the spec, by feature id
(or type), e.g. --set well.state=cleared. Values are parsed as JSON when they can be.
Needs numpy, scipy, pillow. A 20x14 map takes about 15 s.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mapgen import core, features  # noqa: E402
from mapgen.biomes import BIOMES  # noqa: E402


def apply_set(spec, assignment):
    key, _, raw = assignment.partition("=")
    fid, _, field = key.partition(".")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    hits = [f for f in spec["features"] if f.get("id", f["type"]) == fid]
    if not hits or not field:
        raise SystemExit(f"--set {assignment}: no feature with id {fid!r} (or missing .field)")
    for f in hits:
        f[field] = value


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--set", action="append", default=[], metavar="ID.KEY=VALUE")
    a = ap.parse_args()

    spec = json.loads(pathlib.Path(a.spec).read_text())
    for s in a.set:
        apply_set(spec, s)
    biome = BIOMES.get(spec.get("biome"))
    if biome is None:
        raise SystemExit(f"unknown biome {spec.get('biome')!r} (known: {', '.join(sorted(BIOMES))})")
    seed = a.seed if a.seed is not None else spec.get("seed", 7)
    name = spec.get("file") or (spec["src"].rsplit("/", 1)[-1].rsplit(".", 1)[0] if "src" in spec
                                else re.sub(r"[^a-z0-9]+", "-", spec["name"].lower()).strip("-"))

    out = pathlib.Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ctx = core.Ctx(spec, seed)
    feats = features.build(spec.get("features", []), ctx)
    img = biome.render(ctx, feats)
    image_path = out / f"{name}.webp"
    prev = core.save(ctx, img, image_path)
    scene = core.write_scene(ctx, out, image_path.name)
    print(f"wrote {image_path}, {prev}, {scene} "
          f"({ctx.W}x{ctx.H} px, seed {seed}, {len(ctx.scene['walls'])} walls, {len(ctx.scene['lights'])} lights)")


if __name__ == "__main__":
    main()
