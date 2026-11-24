---
name: map-generate
description: Generate an original top-down battle map procedurally from a small layout spec (biome + features placed in grid squares), grid-aligned for Foundry, with a scene.json of walls and lights that build-scene.js can load. Use when an encounter needs a map and there is no map art, or the GM wants one on the fly. Currently has a swamp biome; new biomes, landscapes and cities get added as encounters need them.
---

# Map generate

Writes maps that follow the `map-prep` contract out of the box: 100 px squares, grid phase 0, no grid
baked in (Foundry draws it). The same seed always gives the same map, so a map can be re-rendered later
(for example the same place after the fight) without moving anything placed on it.

Use `map-prep` for existing map art, `foundry-auto-walls` for walls on art we didn't draw, and this skill for
maps we invent. Because we place every feature, the walls and lights come out of the layout, so nothing needs
detecting or tracing.

## Workflow

1. **Design the layout from the encounter** (`daggerheart-encounters`): what is the set piece, where does each
   group start, where is cover and footing, what pulls people toward the middle. Sketch it in squares. 20×14 at
   5 ft is a good default for 4–6 PCs plus a few adversaries.
2. **Write the spec** (copy `examples/thirsty-well.json`). Put trees and other blocking clutter on or past the
   edges, and keep the middle readable.
3. **Generate**: `python3 scripts/generate_map.py SPEC.json OUT_DIR` (about 15 s for 20×14).
4. **Check the preview**: Read `OUT_DIR/<file>-preview.jpg`, which has the grid drawn. Is every feature
   where the encounter needs it, and is the footing readable at a glance? Try `--seed N` for a different
   roll of the same layout. Change a feature without editing the spec with `--set ID.KEY=VALUE`
   (for example `--set well.state=cleared`). Send the user the preview before uploading.
5. **Into Foundry**: serve `OUT_DIR` with Playwright's `page.route` and run
   `foundry-adventure-import/scripts/build-scene.js` (see that skill, "Serve and import"). It uploads the image to
   `src`, creates or refreshes the scene, and adds the walls and lights. Or upload just the image with
   `foundry-vtt/scripts/upload-via-playwright.js` and build the scene in the encounter script. Follow the
   live-world rules in `foundry-vtt` (no pause, no `activate()`).

## Spec

```json
{"name": "The Thirsty O'-Well", "biome": "swamp", "size": [20, 14], "grid": {"size": 100, "distance": 5},
 "seed": 7, "darkness": 0.4, "src": "assets/maps/prismeer/hither/thirsty-o-well.webp",
 "fog": {"edge": 2.0, "strength": 0.42, "patches": 0.10},
 "features": [{"id": "well", "type": "well", "at": [10.5, 6.4], "state": "ooze"}, ...]}
```

- Positions and sizes are in **grid squares** from the top-left corner (fractions are fine, and so are
  points off the map).
- `src` is the Foundry path (see `foundry-vtt/references/conventions.md`), and its basename becomes the
  file name. Otherwise `file`, or a slug of `name`.
- `fog`: `false` turns it off. Otherwise give overrides (`edge` in squares, `color` [r, g, b]).
- `folder`, `journal`, `page`, `global` pass through to `scene.json`.
- `id` is optional and is what `--set` uses. It defaults to the type.

## Biomes and features

| biome | look |
|---|---|
| `swamp` | deep and shallow water, mud, moss, hillshade, reeds on the shallows, lily pads in open water |

| feature | spec | does |
|---|---|---|
| `well` | `at`, `r_outer` 1.25, `r_inner` 0.82, `state` `ooze` / `cleared` | stone ring, mud apron, moat, ripples, foam, trinkets. Ooze adds a green pulse light. Role `focal` |
| `causeway` | `path` [[x, y], ...], `spacing` 0.58, `sunk` 0.13 | raised bed with stepping stones along a smooth curve. Role `path` |
| `hummock` | `at`, `r` | a rise of firm ground (footing and cover) |
| `trees` | `at` [[x, y], ...], `kind` `mangrove` | root tangles under blurred canopies |

Roles let a biome keep its decoration clear: the swamp's reeds and lilies stay off `focal` and `path` features.

## Extending (new biomes, landscapes, cities)

Code lives in `scripts/mapgen/`: `core.py` (canvas, noise, shapes, layer stack, fog, output),
`features.py` (feature types and their hooks) and `biomes/` (one module per biome, listed in
`biomes/__init__.py`).

- **New feature**: subclass `Feature` with `@feature("name")` and implement the hooks it needs: `heights`,
  `footprint`, `water_fx`, `draw`, `scene`. Hook semantics are in the `features.py` docstring. Walls and lights
  go in `ctx.scene` in image px, in the build-scene.js format: walls `[x0, y0, x1, y1, kind]` (1 wall, 2 door,
  3 window, 4 movement only, 5 secret door), lights `{at, dim, bright, color, alpha, anim}`, interiors (polygons
  that darken by day). Anything built of walls, like ruins, buildings or a city block, should emit its walls,
  doors and windows here. That's where this approach saves the most work.
- **New biome**: a module with `render(ctx, feats)` that builds the base terrain, calls the feature hooks it
  supports, draws its own decoration, and returns `fog(ctx, ctx.layers.composite(base), ctx.spec.get("fog"))`.
  Reuse the core helpers. When features from one biome don't make sense in another, check `f.type` and raise.
- **Keep old maps reproducible.** Random numbers are drawn in a fixed order: terrain noise from `ctx.noise`,
  decoration from `ctx.R`. Inserting a draw call before existing ones re-rolls everything after it.
  Add new randomness after the existing calls, or only when a new spec option is set.
  Run `scripts/check_regression.py` after any change to core, features or the swamp. It re-renders the Thirsty
  O'-Well in both states and compares hashes (`examples/regression.json`; re-record with `--update` only after
  an intended change or a library upgrade, checked by eye).
- Add a row to the tables above and an example spec for every new biome or feature.

## Lessons

- Fog at the edges plus a few drifting patches hides the map border and suits 30-ft token vision. Lit areas
  show through fog at any range.
- Keep the floor readable: water vs footing has to be obvious at Foundry zoom, so check the preview at half
  size, not the full image.
- Prefer one map with state variants (`--set`) over a new map when the same place comes back changed (the
  well after the fight became the "Two Truths" chase map).
