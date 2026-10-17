# TTRPG skills

Skills and tools Claude uses to build and run tabletop games in Foundry VTT V14 (developed on the
Daggerheart system). Each folder is a skill: `SKILL.md` (frontmatter `name` + `description`, then
instructions) plus `scripts/`, `references/` and `examples/`.

| skill | use it for |
|---|---|
| [`foundry-vtt/`](foundry-vtt/SKILL.md) | Driving a Foundry world from the browser tab: scenes, Scene Levels, stairs, surfaces, uploads, Daggerheart system quirks, world conventions |
| [`map-prep/`](map-prep/SKILL.md) | Measuring grid pitch/phase and cropping multi-floor maps to identical, grid-aligned canvases |
| [`foundry-auto-walls/`](foundry-auto-walls/SKILL.md) | Auto-detecting walls, doors and windows from a map image (two methods, by map style) and pushing them per level |
| [`foundry-adventure-import/`](foundry-adventure-import/SKILL.md) | Adventure text → GM journals (5etools JSON or supplement PDFs), 5e → Daggerheart mechanics, actor ↔ journal links |

Typical pipeline for a new multi-floor map:
`map-prep` (crop/align) → `foundry-vtt/upload-files.js` → Levels + `create-stair.js` +
`create-surfaces.js` → `foundry-auto-walls` → **lighting pass** (`foundry-vtt/references/lighting.md`) → test like a player.

## Requirements (cloud workspace)

`python3` with `numpy scipy pillow scikit-image skan` (`pip install skan --break-system-packages`).
JS scripts run in the Foundry `/game` tab, either through the Playwright MCP (`browser_evaluate`) or
Claude in Chrome's `javascript_tool`. See `foundry-vtt/SKILL.md` → How to connect.

## Iterating

- When a session learns something (new gotcha, better threshold, new map style), update the
  matching SKILL.md or reference **and** the script, then commit.
- Keep per-map manual corrections as data (`foundry-auto-walls/examples/*-fixes.json`), not as
  hand-edited output.
- Scripts take **image-pixel** coordinates. The Foundry scripts add the scene padding offset.

## Changelog

- 2026-09-24 — First version, extracted from the Bavlorna's Cottage build:
  Scene Levels, two-way stairs (level tags + unbounded elevation), surfaces with stair holes,
  auto-walls (163 walls / 21 doors / 13 windows over 3 floors), grid-phase alignment, browser upload
  pipeline.
- 2026-09-24 — Loomlurch: `detect_rooms.py` (walls from floor regions, for maps without a
  distinct wall colour; filters dashed callout lines), `create-scene.js`, the 10 ft grid lesson,
  and a file_upload path gotcha (files must be under the working dir).
- 2026-09-24 — Loomlurch insets: teleport stairs with landings (`create-teleport-stairs.js`), ring
  walls around inset circles (`create-ring-walls.js`), region behavior/restriction/shape catalogue.
- 2026-09-24 — Lighting pass is now a standard prep step: `rooms_from_walls.py`,
  `create-room-lights.js`, `references/lighting.md`. Applied to Loomlurch and Bavlorna's Cottage.
  Fourth Loomlurch teleport pair (the pumpkin-patch stair).
- 2026-09-24 — Day/night: global light max 0.5 on every map, interior regions in DARKEN mode (not
  override), night-only exterior lights (`exterior_openings.py`, `create-exterior-lights.js`). Tested with darkness 1.
- 2026-09-24 — Motherhorn (4 levels): black-outline wall profile (`thick_mode: erase`, `min_cluster_extent`),
  `find_sconces.py` lighting from map markers, 3-level stair dialog, grid-aligned region rule, wall-constrained
  token updates, JSON upload through the file input.
- 2026-09-24 — Motherhorn walls v2 after the GM's review (clusters along walls, holes): `mask: outline`
  (disk opening), `merge_collinear`, `bridge_gap`, kind-4 `sky_edge` walls. 3,046 → 1,604 walls, cleaner.
- 2026-09-24 — Doors: `door_merge_gap` + `door_segments: rect` (one door per doorway, double doors merged).
  Open-air shafts: edge-wall railing + surface hole (Motherhorn Tower 2 pit).
- 2026-09-24 — Motherhorn review #3: `door_connect` (doors touch walls), no wall bridges across doors, re-crop
  from the full page with an island mask (tower 1 was cut), 10 ft grid (read the legend!), fill lights for unlit rooms.
- 2026-09-24 — Motherhorn stairs: curved front stairs are Stage ↔ Tower 1 (identical art on both levels), not T1 ↔ T2.
- 2026-09-24 — Cross-level teleport stairs (landing elevation band clamps elevation). Level menu scrolls (Understage 'missing').
- 2026-09-24 — Palace of Heart's Desire (4 levels): `white_windows` for crenellated walls, placeholder runs for the cluster
  filter, inset floors pasted as levels, programmatic ring walls for tower insets.
- 2026-09-24 — Palace: storm courtyard open between Lower/Upper (surface hole + island surface), lightning lights, garden night lanterns.
- 2026-09-24 — Palace walls v2 after review (many interior walls missing): `sandwich` detector for double-outline walls
  (clipped to the building box), `grid_walls.py` fallback. ~1,900 → ~5,800 walls on the two main floors.
- 2026-10-03 — Palace review #3: hand-traced perimeter (examples/palace-perimeter.py), `chain_openings`, `veto`,
  and the light coverage fill.
- 2026-10-03 — Palace review #4 (missing interior walls, messy map-key symbols): `postprocess.py` (markers + Hough
  rings), `review_crops.py` + `apply_fixes.py` (review as data: remove/add/arcs/drop_on_floor/prune), bedroom
  blocks rebuilt as rectangles, carpet/pew false walls removed. Lower+Upper: 5,786 → 5,045 walls.
- 2026-10-04 — Palace review #5: `apply_fixes.py` gains `dedupe_parallel` (walls over doors, double lines), `cuts`
  (open ramp/bridge mouths; 8 storm-court ramps), `rebuild` (one clean wall along a messy perimeter side);
  `replace-auto-walls.js`. Lower+Upper: 5,045 → 3,610 walls.
- 2026-10-17 — `foundry-adventure-import`: 5etools chapter → compendium journal (pages, keyed-area anchors, map image
  pages, environment links), 5e → Daggerheart conversion rules + review/overrides loop, browser-side image upload,
  actor 📖 back-links. Playwright MCP documented as a second transport. First chapter: Witchlight ch. 2 (Hither).
- 2026-10-17 — Play content moves to the world (`move-packs-to-world.js`). Adventure import: a page per keyed area,
  RollTables via `@Embed`, NPC autolinks, GM-only semi-transparent area pins aligned with SIFT (`align_maps.py`,
  `create-area-notes.js`). Bavlorna's Cottage: 20 pins on 3 levels.
- 2026-10-17 — Supplements: `pdf_to_fivetools.py` (PHB-style PDFs → 5etools-like JSON), `create-docs.js`, `page_prepend`,
  `import.json` options, Daggerheart creature-conversion guidelines. First: The Watcher's Pool (journal, 4 actors, environment, item, handout).
- 2026-10-17 — Thither: book chapter, 3 supplements, 4 supplement scenes from hand-traced specs (`scene_from_spec.py`,
  `build-scene.js`), hidden tokens per area (`plan_tokens.py`, `place-tokens.js`), handouts, world→compendium sync
  (`sync-world-to-packs.js`), Playwright `page.route` instead of a file server, regex/page/table overrides.
- 2026-10-17 — Lean adversaries (3–5 features). Hither complete: Slanty Tower + Brigands' Tollway supplements, scenes for
  Downfall (book player map + regions), Watcher's Pool, Slanty Tower floors, Tollway interior, Ixjharatar's den. `open` polygons.
