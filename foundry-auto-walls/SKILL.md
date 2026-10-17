---
name: foundry-auto-walls
description: Auto-detect walls, doors and windows in a battle-map image and create them as Foundry VTT V14 walls (per Scene Level). Use when a Foundry scene needs walls from a raster map instead of hand-drawing them.
---

# Foundry auto-walls

Turns a raster battle map into Foundry Wall documents: **walls** (block everything),
**doors** (closed, clickable) and **windows** (block movement, see-through). Good for
80–90% of the work; expect a handful of manual fixes per floor. "No perfection needed"
is the agreed bar — ship it, then let the GM nudge walls in the Walls tool.

Depends on the `foundry-vtt` skill for connecting to the Foundry tab.

## Pick the method by map style

| map style | tool | example |
|---|---|---|
| Walls are a distinct colour/texture band (stone, plaster) | `scripts/detect_walls.py` (wall pixels → skeleton) | Bavlorna's Cottage, `examples/bavlornas-cottage-fixes.json` |
| Walls are thick BLACK outlines on grey rock (Motherhorn) | `detect_walls.py --profile examples/profiles.json:motherhorn` (`mask: outline`, `merge_collinear`, `bridge_gap`, `sky_edge`) | Motherhorn, `examples/motherhorn-fixes.json` |
| Stone walls with CRENELLATIONS and white window slits (Palace of Heart's Desire) | `detect_walls.py --profile examples/profiles.json:palace` (`white_windows`, `close: 13`) | Palace, `examples/palace-fixes.json` |
| Walls are NOT distinct (rooms carved into bark/rock, walls = outline between floor and surroundings) | `scripts/detect_rooms.py` (floor regions → outlines) | Loomlurch, `examples/loomlurch-rooms.json` |

`detect_rooms.py` is semi-automatic on purpose: `label` colours every floor-like region with an id,
you look at `rooms-labels.png` and choose the real rooms (`--keep`), then force clean shapes for
ragged rooms (`--rect`, `--circle`). Dirt clearings and paths often match the floor colour, which is why
a human or Claude has to choose. Callout dashes (the dashed lines to inset circles) look exactly like
doors; the script drops any white bar that has a sibling bar 55–120px away along its own axis.

## Workflow

1. **Get the exact images the Levels use** (same pixels as `Level.background.src`). If they
   were made with `map-prep`, they are already in the workspace; otherwise download them from
   the Foundry tab (fetch the asset URL in JS and pass it back as base64, or stage from the
   user's folder).
2. **Calibrate colours if this is a new map style.** Sample a wall, a door, a window, floor
   and the outside background:
   `python3 scripts/detect_walls.py --sample X,Y --sample X,Y L1=floor.webp`
   Put overrides in a profiles JSON (`--profile profiles.json:name`); only keys that differ
   from `DEFAULT_PROFILE` are needed. The default is tuned for the *Wild Beyond the
   Witchlight* book maps.
3. **Detect:**
   `python3 scripts/detect_walls.py --out work/walls.json L1=l1.webp L2=l2.webp L3=l3.webp`
4. **Review every `overlay-KEY.png`** (Read it; downscale to ~1000px wide first if large).
   Red = wall, blue = door, cyan = window. Typical misses:
   - windows whose glass colour was not detected (look for gaps in exterior walls)
   - exterior stairwell boxes and thin-outlined balconies/bays (not stone-coloured)
   - walls at the image edge on floors with transparency (e.g. a rounded upper floor)
   - junk clusters on rugs, tables, frosted floors → `remove_boxes`
5. **Record fixes in a fixes JSON** (`--fixes`) rather than hand-editing walls.json, and
   re-run. That keeps the result reproducible. See `examples/bavlornas-cottage-fixes.json`.
6. **Push:** fill `scripts/push_walls.js` (SCENE, LEVEL_NAMES, WALLS) and run it with
   `javascript_tool`. For more than ~5 KB of JSON, send it in chunks to `window.__W` first. It deletes walls previously pushed to those levels (REPLACE) and adds the
   scene padding offset. Then **verify in the canvas**: `canvas.walls.activate()`, switch
   to each level, and take a screenshot.

## Black-outline maps (Motherhorn) — lessons

The first pass (thin-line tolerant mask) was bad. The GM checked it in Foundry and found star-shaped clusters of tiny
segments around the rivets and furniture along the walls, plus holes. They redrew two samples by hand: long
straight walls and smooth arcs. v2 matches that, uses half the walls (~1,600 vs ~3,000 over 4 floors), and passed
the stair test.

- **`mask: "outline"`**: a DISK opening (`open_disk: 3`) keeps only bands ≥ 7px thick. Walls survive, while rock
  cracks, rivet/stud outlines, furniture outlines and grid lines disappear. Then drop blobs whose bounding
  box is < `min_blob_extent` (60px). Test it on a crop first: view `dark` vs `opened` side by side.
- **`merge_collinear: 8`** merges consecutive segments that bend < 8° (16° between short pieces), which turns
  skeleton staircases into single long walls. Arcs stay as short chords.
- **`bridge_gap: 45`** connects a dead-end wall end to the nearest wall point ahead of it (or within 15px)
  to close the holes.
- **`sky_edge`** adds kind-4 **edge** walls (block movement only) along the border with the blue sky, so
  tokens can't walk off balconies and cliffs whose parapets are grey rather than black. `open: 15`
  removes lightning bolts. Banners and art in the sky get edges too, which is harmless.
- **Dark-brown props** (the stage machinery beams) pass the dark mask. Remove them with a `remove_boxes`
  fix. **Double doors** are up to ~200px long (`door_len: [35, 210]`). Doors missed on a floor go in
  `add` (see `examples/motherhorn-fixes.json`).
- **Double doors = one door.** `door_merge_gap: 15` closes the thin black line between two white leaves, and
  `door_segments: "rect"` emits exactly ONE door per door blob along its long axis (minAreaRect). Skeletonising
  filled door rectangles produced stubs and zero-length pieces, which showed up as 2–5 door segments per doorway
  (the GM's screenshot). Motherhorn went from 48 fragmented door pieces to 16 real doors.
- **Doors must touch walls.** `door_connect: 40` links every door end to the nearest dead-end wall endpoint
  (or the nearest point on a wall) within 40px. `bridge_gaps` never draws a link that crosses a door, because
  otherwise it walls off the doorway. Without this, 10–30px slits beside doors leaked light and vision.
- After pushing, **delete non-door walls inside changeLevel squares**. The keyhole ring around a spiral stays,
  and the neck stays open.
- Always look at the overlays at full resolution on a few crops (a room with wall ornaments, a curved wall)
  before pushing. The downscaled overview hides this kind of mess.
- For big walls.json files, upload the JSON through the same hidden file input as the images and
  `JSON.parse(await file.text())` in the page.

## Crenellated walls with window slits (Palace) — lessons

- Outer walls are merlons separated by **white window slits** (~24–40px, often rotated on round towers). Without
  help, each merlon is a separate small blob and gets dropped, so whole outer walls vanished.
- **`white_windows: [min, max]`** finds white blobs shorter than a door (rotation-aware `minAreaRect`, thickness
  4–16, near the stone). They're added to the wall mask **before** cleaning (dilated by `white_window_join`, 8)
  so the band stays connected, and emitted as kind-3 windows.
- During vectorising, door/window runs are kept as **placeholders** (negative kind) so the small-cluster filter
  sees one connected wall. They're dropped afterwards, and the real doors/windows come from `door_rects()`.
  `door_connect` links windows to walls as well.
- `close: 13` bridges the thin gaps between merlons, and `wall_max_half_thickness: 28` allows thick outer walls.
- Blocks of rubble on the floor produce junk walls, so remove them with `remove_boxes`.
- Round towers drawn as INSETS (a separate floor on the same page) get programmatic ring walls: outer ring, inner
  ring with a door gap. That's faster and cleaner than detection on 600px circles.
- `sky_edge` with `RETR_LIST` also traces holes. On the Palace, the storm courtyard and the clouds produced
  thousands of junk edges, so I didn't use them. Ask the GM how the storm should behave instead.

## Thin double-outline walls (Palace interiors) — `sandwich`

The GM found many Palace walls missing after v1: the interior walls are **black line / pale core / black line**
(~15–20px), too pale for the stone colour mask and too thin for a disk opening. Loosening the stone colours just
picked up the marble floor. What works is **`sandwich`**: a pixel is wall core when a dark run of ≥3px lies within
`reach` (15) px on BOTH sides of it (above and below, or left and right). The drawn grid is a 1px black line, so it
never qualifies. Settings: `{"dark":40,"min_run":3,"reach":15,"min_extent":100,"erase_half":14,"box":[x0,y0,x1,y1]}`.
- **`box` is essential.** Without it the gardens, vines, trees and page frame exploded into 15,000 walls. Clip to the
  building footprint (per level: profiles `palace_L1` / `palace_L2`).
- Door interiors are sandwiched too (white between black outlines), so subtract the dilated white mask.
- Remaining junk: spiral stair drawings, pews, long tables, beds, beanstalk vines, the central tower's ring stair.
  Handle it with `remove_boxes` and a radial filter for ring stairs. Expect ~2,700–3,000 walls per floor on a
  palace-sized map.
- `scripts/grid_walls.py` (walls on grid edges with a dark run ≥3px) was tried first. It finds some real walls but
  also stair steps and furniture, and only axis-aligned ones on the grid, so `sandwich` replaced it. It's kept as a
  fallback for very clean grid-aligned maps.

## Exterior walls: trace the perimeter by hand (Palace review #3)

Crenellated outer walls kept failing: the merlons between window slits and diagonal or rotated walls with rotated
slits were missed, so the GM saw rooms open to the sky. Automatic silhouettes (sky/cloud masks, stone masks)
were worse. Clouds next to the walls are grey, and vines and page art join the shape. **What works is tracing the
perimeter by hand from grid-labelled crops** (100px grid, 500px labels, 4 quadrant crops per floor). It takes
about 25 vertices plus arcs for round towers (`arc(center, r, p0, p1, through)`). Cut the perimeter where a
detected door or window sits, so they keep working. See `examples/palace-perimeter.py`. It takes about 10 minutes per
floor and is worth it for any building with ornamented exterior walls.
- `chain_openings: 130` (profile) links each window/door end along its axis to the next opening or wall ahead,
  which fills merlons in straight crenellated runs. It's cheap and helps, but doesn't replace the traced perimeter.
- `veto: {"box": [...], "green": 15}` drops walls outside the building box (the page's corner lion art) and walls
  sitting on vegetation (vines). Vines INSIDE the building (the beanstalk tower) still leave junk. The GM finds
  that tolerable.

## Map-key markers, round rooms, and the review loop (Palace review #4)

The GM still found missing interior walls and "complicated" walls around the map-key symbols (white ovals with a
stag/lion silhouette and a pointed callout). Two scripts finish what detection leaves:

- **`scripts/postprocess.py`** — (1) finds the marker ovals (white, ~110×135px, with holes) plus their pure-white
  callout triangles, deletes kind-1 walls inside that zone (hull + 12px), and reconnects a straight wall the marker
  sat on; (2) Hough circles at 0.5× (validated by ≥70% dark pixels on the circle, `--ring-exclude` boxes for vines and
  art) add the missing pieces of round-room outlines. Process markers in windows and use distance transforms. The
  first full-image version ran >10 minutes.
- **`scripts/review_crops.py`** — 3×3 labelled crops of the building (100px ticks). Read every crop and list
  misses/junk with image coordinates (`X = crop_x0 + px/scale`). Confirm each wall line with a pixel profile
  (print a row/column as `#`/`+`/`.`) before adding it. That takes a couple of minutes and avoids walls 15px off.
- **`scripts/apply_fixes.py walls.json fixes.json --out ... L1=img`** — applies the review as data
  (`examples/palace-review-fixes.json`): `remove` boxes (midpoint rule, kinds filter), `add` segments (ends snap to
  existing endpoints), `arcs` (centre/radius/angles, window slits found automatically along the band),
  `drop_zero` (degenerate openings that chain_openings had linked diagonally across rooms), `drop_on_floor`
  (kind-1 walls lying on open pale floor or clouds), `prune_spurs` (short dead ends).

What the review found on the Palace, so check these first on similar maps:
- A wall drawn as **one thick black line** next to a different floor texture (grey flagstones | corridor) isn't a
  sandwich, so it's missed. Add it by hand.
- A wall **with a bench along it** (chapel, pew corridor): the detector follows the bench outline 10–25px off the
  wall, or the bench breaks the run. Remove it and re-add the true line.
- **Carpet/rug borders** (the long purple runner) and **pews / long tables** become long false walls. Remove them with boxes.
- **Bedroom blocks** full of beds, desks and rugs come out as zigzags. Faster: remove every kind-1 wall inside each
  room (keep doors/windows) and re-add the room rectangle from profiles.
- A **hand-traced arc** can land on the outer edge (in the clouds). `drop_on_floor` flags it, so re-fit the circle
  from two profiles (top and side of the band).

Review #5 (same day) added three more `apply_fixes.py` ops, all generic:
- **`dedupe_parallel`** drops a kind-1 wall that runs within 16px of, and ≥70% alongside, a door, window or longer
  wall. That fixes **walls lying over doors** (the sandwich/perimeter line next to a door blocks it) and the double
  lines of thick walls. It removed ~500 walls per Palace floor with no gaps.
- **`cuts`** opens a passage: walls crossing a band (`width`) around an axis lose that piece. Use it for **ramps and
  bridges** whose ends meet a round room's ring or a crenellated wall (the Palace storm-court ramps). Derive the axis
  from the two rail walls, not by eye. A 50px error left half of a mouth blocked.
- **`rebuild`** replaces a messy straight wall (double perimeter + detected line + X crossings + bone junk) with
  one clean wall along a line. It keeps the openings sitting on it, drops bogus ones (offset > 12px or longer than
  80px), and re-attaches walls that dead-end against it.
- Push with `scripts/replace-auto-walls.js`. It deletes only `flags.claude.auto` walls on the listed levels, so hand
  edits survive, then clears stair squares.
- Review #6 ops:
  - **`collapse_loops`** replaces tiny closed loops of walls (≤90×35px) with one segment along the loop's long
    axis. It becomes a window if the loop encloses white slit pixels, which handles **window slits on curved walls**:
    the detector draws a box around the slit instead of a window. Without it, light leaked and doors looked boxed in.
  - **`join_dead_ends`** joins mutually-nearest dead ends ≤90px apart if the link crosses no wall, isn't over open
    floor, and isn't in a `cuts`/`protect` passage. That closes the **holes** the GM found in curved walls.
  - **`bays`** handles **balconies** (half-disks outside a door): the parapet becomes an edge arc (kind 4, blocks
    movement but not sight), the tangle at its base is cleared, and the arc ends are tied to the door.
  - **`remove_annulus`** + `arcs` handle **ring staircases**: clear the junk ring and draw one clean inner arc.
- The GM asked whether **art shadows** stop wall creation. They don't, but a room edge drawn as a single black line
  between two floor textures (grey flagstones | white floor) isn't a sandwich. Add those by hand from a profile.

## Why the pipeline looks like this (lessons learned)

- **Close before open.** Stone walls have dark crack texture, so the raw mask is full of holes.
  Opening first (to kill grid lines) erased almost every wall. Close(5) then Open(7) works.
- **Blob filter = thickness, not area.** Rugs, pools and frosted floors pass the colour test.
  Walls are thin, so drop components whose distance-transform max is > ~13px.
- **Doors = pure-white rectangles** that pass a fill-ratio and size test. The opening also
  removes white stair arrows.
- **Windows = gaps in a wall bridged by a 1-D closing that contain glass-coloured pixels.**
  Gaps without glass are left open (archways).
- **The small-cluster filter must only apply to walls.** Door segments often aren't
  endpoint-connected to walls yet. Filtering them as tiny clusters once deleted *every door*.
- **Snap door/window endpoints to wall endpoints (≤25px).** Otherwise 15–20px slits next to doors
  leak vision and light.
- Endpoint clustering (7px) and axis snapping (7% slope) make the result look hand-drawn.
- Curved walls (rounded rooms) come out as short polyline chains, which is fine.

## Foundry specifics

- Walls in V14 have a `levels` field (a Set of Level ids). Always set it, or the wall
  applies to the wrong floors.
- Wall `c` is canvas coordinates: image px + `scene.dimensions.sceneX/sceneY` (padding).
- The Wall schema has `c, levels, light, move, sight, sound, dir, door, ds, doorSound,
  threshold, animation, flags`.
