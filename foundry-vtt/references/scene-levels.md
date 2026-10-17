# Foundry V14 Scene Levels — field notes

Verified live on core V14 (build ~367/368), Bavlorna's Cottage (3 floors), Sept 2026.

## Documents

- **Level** (`scene.levels`): `name`, `elevation {bottom, top, base}`, `background.src` (the
  "Texture" field in the Levels config), `visibility.levels` (which other levels are visible
  from this one — self-only for stacked floors).
- **Region** (`scene.regions`) schema keys: `color, elevation{bottom,top,topInclusive}, levels
  (Set of Level ids), restriction, attachment, visibility, highlightMode, displayMeasurements,
  hidden, name, shapes[], behaviors[], locked, ownership, flags`.
  - The level tag is the core `levels` field, **not a flag** (`flags` is `{}`).
  - `shapes[]` items: `{type:"rectangle", x, y, width, height, rotation, hole}`. `hole:true`
    subtracts from the region.
- **Wall**: `c, levels, light, move, sight, sound, dir, door, ds, doorSound, threshold, animation, flags`.
- **Token**: `token.level` (Level id) + `token.elevation`.

## Suggested elevation bands

Ground 0–10, Second 10–20, Third 20–30 (ft). One band per floor. Keep the grid at 100px = 5ft.

## Stairs (`changeLevel`)

```js
{ name, levels: [idA, idB], elevation: {bottom:null, top:null},
  shapes: [{type:"rectangle", x, y, width:100, height:100}],
  behaviors: [{ type:"changeLevel", system:{ movementActions: [] } }] }   // [] = any action
```
Bugs we hit:
1. **Tagged on only one level.** Then it only works from that level. Tag *every* level it connects.
2. **Bounded elevation (e.g. 0–10, topInclusive false).** Tokens on the upper floor (elev 10) are
   outside the band, so you can go up but never down. Use `null/null`; `levels` already scopes it.
3. **Regions must sit on grid squares.** Round the image-px position to a multiple of the grid size
   (100), or the token (which snaps) never fully enters it. Motherhorn's first stair at (775,920) straddled 4 squares.
4. **Stairs connecting 3+ levels** (Motherhorn spiral: Stage ↔ Tower 1 ↔ Tower 2) get a dialog with a
   **Destination Level** dropdown and a Movement Action. Tested: Stage → Tower 2, elevation 10 → 30.
5. **Which levels does a stair connect? Look for the SAME stair drawn on two levels.** Motherhorn's curved stairs
   outside Tower Level 1 are drawn identically at the front of the Stage (same squares after alignment), so
   they connect Stage ↔ Tower 1. I first guessed Tower 1 ↔ Tower 2, but Tower 2 has no stairs there (the GM
   corrected it). Put the changeLevel square at the stair's far end (the top of the curve), and delete the
   move-only sky-edge walls that trace the stair drawing on the upper level so the path is open. Then test both
   stairs with a token.
6. **Player UX:** entering the region pops a confirm dialog ("Do you want to move X to Second
   Floor?" → Move Down / Don't Move). Nothing happens without the click. `movementActions` can
   restrict it (e.g. only `walk`, so flyers ignore it).

## Teleport stairs BETWEEN levels (when the art doesn't line up)

Book maps often draw a level offset from the one above it, so a stair's two ends don't land on the same
squares (Motherhorn: the Stage's straight stair ↔ the Understage's top-right stair). Use `teleportToken` with
landings on different levels. The teleport **does switch the token's level, but keeps its elevation**
(Stage 10 → Understage showed elevation 10). Fix: give each **landing region an elevation band inside its
level** (e.g. `{bottom:0, top:5}` on the Understage, `{bottom:10, top:15}` on the Stage), and the token's
elevation gets clamped to it. Tested both ways: 10 → 0 → 10.

## The level menu scrolls

The scene-levels menu in the top-left is only ~120px tall (about 3.5 rows) and scrolls. With 4+ levels the bottom one
(Motherhorn's Understage) is hidden and looks "missing". The "G" marker (which level the GM is viewing) takes
up a partial row too. Scrolling isn't obvious to users. Check `scene.levels` before assuming a level was lost.
Fix (per browser session, until a module holds it): inject
`menu.scene-levels{height:auto !important;max-height:none !important}` as a `<style>`. Core Foundry has no
custom-CSS setting, so making it permanent needs a tiny module or a CSS module.

## Surfaces (`defineSurface`)

`system: {placement:"bottom", light, move, sight, sound, occlusion: true, exposure:false, culling:false}`.
Makes the floor solid: tokens on one floor don't see or hear the other floors, light doesn't leak
through, and the surface marks where a floor exists. Without it, dynamic vision can see
across floors. A full-floor surface **covers the stair regions, so the GM can't click them**. Fix:
punch holes in the surface where the stairs are (realistic, too: the stairwell has no floor).
`create-surfaces.js` does this and is safe to re-run. Punch holes for teleport stairs and landings too, not only
changeLevel regions, or the GM can't click them.

## Open-air shafts (a pit/atrium over the floor below)

The map art can't tell you this, so ask or read the adventure. Motherhorn's Tower Level 2 has a central pit
open over the Tower Level 1 machinery. Treat it like this:
- Replace the pit's inner rim walls with **edge walls** (move only, sight/light/sound 0), so nobody walks
  into the air but light and sound pass.
- **Punch a hole in the upper level's `defineSurface`** over the shaft (a `circle` shape with `hole:true`), so
  sight and light reach the level below.

## Inset / "unfolded" floors on one image (Loomlurch)

Some book maps draw the upper floors as **inset circles on the same image**. Don't build Scene
Levels for these. Instead, on the single level:
- **Stairs = `teleportToken` regions** (`scripts/create-teleport-stairs.js`). Each stair teleports to a
  **landing** region next to the *other* stair. Teleporting straight onto the other stair would fire
  that stair again. Use `system: {destinations: Set<regionUuid>, placement: "center"|"random"|"relative",
  snap, choice: true}`. `choice:true` shows "Do you want to teleport X to <region>?" (Teleport /
  Don't Teleport). Tested both directions.
- **Separation = a ring of walls on the inset's border** (`scripts/create-ring-walls.js`). Find the rings
  with Hough circles on a 0.25× HSV mask of the golden border
  (`H 12–32, S>120, V>170`, `minRadius 60, maxRadius 160` at 0.25×). Throw away false circles by eye.
- A Region `restriction` exists (`{enabled, type: light|darkness|sight|sound|move, priority}`), but it
  has one type per region, which is why we use walls for full separation.
- Available region behavior types (V14): adjustDarknessLevel, applyActiveEffect, changeLevel,
  defineSurface, displayScrollingText, executeMacro, executeScript, modifyMovementCost, pauseGame,
  suppressWeather, teleportToken, toggleBehavior. Shape types: rectangle, circle, ellipse,
  emanation, cone, ring, line, polygon, token, grid.
- The stair squares themselves are placed by hand after looking at zoomed crops (stair arrow tips
  line up between the main map and the inset). The skill doesn't automate this. The GM moves regions
  if needed.

## Creating a scene with levels

`Scene.create({..., levels: [{name, elevation:{bottom,top}, background:{src}}]})` works in one call.
Then set `initialLevel` to the first level's id (reading `scene.initialLevel` returns the resolved
Level object). A Level object also carries `foreground`, `fog`, `visibility.levels` and a
`textures` block `{anchorX, anchorY, offsetX, offsetY, fit:"fill", scaleX, scaleY, rotation}`.
Texture offset and scale therefore *exist* on the Level, but we haven't tested them. Pre-aligned,
identical-size crops are still the reliable path.

## Level textures vs. Tiles

The Level "Texture" is simpler for players and GMs (it switches with the level), but it **always fills
the scene**. The first Bavlorna build used Tiles. The user switched to textures, so all floor
images had to be re-cropped to the same size and the same grid phase (grid off by 0.4 of a square
before re-measuring). Tiles only make sense for pieces that are smaller than the scene.

## Padding

`scene.padding` (0.05 here) shifts the scene area: `dimensions.sceneX/sceneY` (200/100 for a
2100×1700 image). Image px + offset = canvas px.
