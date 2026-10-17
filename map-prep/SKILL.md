---
name: map-prep
description: Prepare battle-map images for a VTT. Measure the grid pitch and phase exactly, then crop and scale one or several floors to identical, grid-aligned canvases (100px per square, grid at 0,0). Use before putting any map into Foundry, especially multi-floor Scene Levels.
---

# Map prep

## Why

Foundry V14 Level textures fill the whole scene (no offset or size), and the Foundry grid starts at
the scene origin. So each image must:
1. have its grid lines at x = k·100 and y = k·100 (**phase 0**, **pitch exactly 100px**)
2. be the **same size** as the other floors of the same scene
3. place shared features (the stairwell) on the **same squares** on every floor

Eyeballing the crop gave a grid that was "close but not perfect" (off by about 40px). Always measure.

## Tools

- `scripts/grid_phase.py IMG [--box x0,y0,x1,y1]` prints pitch and phase (sub-pixel) from
  gradient-energy autocorrelation and a comb search. Use `--box` on book pages so text and margins
  don't dominate. A phase of 99.5 is the same as −0.5, which means aligned.
- `scripts/crop_floors.py config.json` measures each source, positions it by an **anchor**
  (a shared feature in source px mapped to `anchor_out` in output px), snaps it to the grid phase,
  scales it to `target_pitch`, and pads outside areas with transparency. See the docstring for the
  config format.

## Crop from the ORIGINAL page, and check nothing is cut

Motherhorn's first tower-1 crop (inherited from an old pass) was cut off at the bottom and lost a round room,
a balcony and a floating platform. The GM noticed it in play. Always:
- locate each crop in the full source page (`cv2.matchTemplate`, first at 0.25×, then refine at full res),
- build the floor from the page with a **land mask**: non-sky pixels (`B-R <= 35`), opened/closed 15px,
  clipped to a box around the floor, keeping only the connected components that belong to that floor
  (a seed point per island). Other floors' islands, the title banner and the frame must NOT connect, so
  choose the box so they don't,
- compare the resulting alpha bbox with what you see on the page preview.
- **Read the scale legend on the page** ("1 square = 10 feet" on Motherhorn). Motherhorn was built at 5 ft by
  mistake. When changing `grid.distance` later, rescale light `dim`/`bright` by the same factor.

## Insets as separate levels (Palace upper floors)

When a page draws small floors as insets (the Palace's "Central Tower, Third/Fourth Floor" and "Beanstalk Tower,
Upper Floor"), cut each inset with a circular mask and paste it at the position of the same tower on the main
floor (Hough circle centres on both). Several insets can share one level if they're at the same height and don't
overlap (Third Floor = central tower L3 + beanstalk tower upper). Then **measure the grid phase of each pasted inset
in its own box** and shift it by the phase error (inset grids aren't aligned with the main page).

## Choosing anchors between floors

Use a **cross-section handout** if the book has one (Motherhorn's shows which floors stack). Anchor on a
feature that is drawn on BOTH floors: a spiral stair, a round tower drawn from above, a stairwell. Floors
that only touch through one stair chain their alignment through it (Understage ↔ Stage via the round
tower; Stage ↔ Towers via the spiral). Check with a 50% blend of each neighbouring pair. Hough circles on
the grey image find round towers quickly (minRadius ~120 at full size).

## Workflow

1. Stage the source images (book page exports, map packs) into the workspace.
2. Find each floor's grid box and one shared anchor (for example the centre of the stairwell) by viewing
   downscaled previews. Read them, and zoom into crops to pinpoint the anchor.
3. Write the config with a `frame` big enough for the largest floor, and run `crop_floors.py`.
4. Verify: run `grid_phase.py` on every output (pitch ≈ 100, phase ≈ 0). Make a contact sheet or
   blend two floors at 50% to check that the stairwell overlaps. Send the user a verification image.
5. Upload with `foundry-vtt/scripts/upload-files.js` and set them as Level textures. Set scene
   width/height to the frame size, grid 100px, and distance from the map legend (5 ft or 10 ft).

## Known state (Sept 2026)

`grid_phase.py` on the Witchlight crops already in Foundry: **Bavlorna v2 = aligned**.
**Motherhorn = aligned** (4 floors, 3300×3800, anchor = the spiral stair centre shared by Stage and both
Tower levels. The Understage is anchored off the round tower, which appears on both Understage and Stage.
See `examples/motherhorn-crop.json`. Anchors can be negative or outside the source image).
**Loomlurch = re-cropped and aligned** (3800×5300, uploaded over the old file). **Palace of Heart's Desire = aligned** (4 levels at 4000×5500, 10 ft, rebuilt from the two full pages; the lower and upper pages
register exactly, and the insets are pasted onto their towers).
If the source is an already-cropped 100px map, a single-floor config without `frame` just trims
the partial edge squares.
