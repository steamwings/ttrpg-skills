# Lighting pass (part of preparing EVERY map)

The user asked for this explicitly: no map is "done" without lights. Do it after walls, because lights
are clipped by walls (`walls: true`).

## Day/night rule (works with "Transition to Darkness / Daylight" on every map)

- **Global light is always on, with `darkness.max 0.5`.** Outdoors is lit by day and goes dark from dusk on.
- **Interiors get an `adjustDarknessLevel` region in DARKEN mode (mode 2, modifier 0.7).** It follows the
  scene: by day the interior sits at 0.7 (above 0.5, so no global light inside, only room lamps), and at night
  it reaches 1. Don't use OVERRIDE: it's static and breaks the transition. The first Loomlurch pass used
  override 0.8, then got switched.
- **Room lights: always on** (darkness range 0–1).
- **Exterior lights: night only** (`config.darkness {min 0.45, max 1}`). Put lanterns outside exterior doors,
  glow outside windows, and hand-placed lanterns at camps and stalls. Use `scripts/exterior_openings.py` and
  `scripts/create-exterior-lights.js`.
- The starting darkness is just the mood. Tested on Loomlurch at darkness 1: the lanterns switch on, the rooms
  stay warm, and outside is dark.

## Steps

1. **Pick the mood from the setting**, not by default. Ask if the fiction is unclear.
   | situation | darkness | global light |
   |---|---|---|
   | outdoors in the afternoon with interiors (Loomlurch) | 0.3 | on, max 0.5 + Interior region (darken 0.7) |
   | indoors / dusk (Bavlorna's Cottage, Hither) | 0.6 | on, max 0.5 + Interior region per level (darken 0.7) |
   | night / dungeon | 0.85–1.0 | on, max 0.5 (it only matters if someone transitions to daylight) |
2. **Find rooms.**
   - Wall-based maps: `scripts/rooms_from_walls.py walls.json --size WxH --overlay KEY=img` rasterises
     walls and doors, drops the outside, and places each light at the point farthest from any wall
     (a centroid can fall outside L-shaped rooms). Rooms with a leak merge with neighbours or the
     outside. Review `rooms-KEY.png`.
   - Floor-region maps (`detect_rooms.py`): reuse the kept regions. Centroid, equivalent radius and
     polygon come from `room_outline`.
3. **If the map draws its own lamps, use them.** Motherhorn marks every sconce with a red dot:
   `scripts/find_sconces.py` found 102 of them (dropping the theatre seats as dense clusters). Push them as
   small torches (dim 15 / bright 5 ft, `#ff6a3d`), then add room fill lights by eye (big halls, the stage).
   On black-outline maps with ~3,000 walls, `rooms_from_walls.py` is too leaky to trust.
4. **Every room gets light.** After sconces, run `rooms_from_walls.py` and add a warm fill light to each
   room that contains no sconce. Rooms joined by open doorways (curtains) merge into one big region and get
   skipped, so look at the lit scene and add lights by hand where it's still dark (Motherhorn's stage-left
   bedrooms were missed this way).
5. **Add practical lights by eye** where the art shows a source (chandelier, hearth, brazier,
   glowing pool). The script finds rooms, not lamps.
6. **Exterior pass:** `exterior_openings.py walls.json --size WxH --overlay KEY=img` finds doors and windows
   with indoors on one side and outdoors on the other, and returns a point just outside each one. Check the
   overlay: a point inside an undetected room is a false positive, so drop it. Add kind-4 lanterns by hand
   for camps and stalls, then push with `create-exterior-lights.js`.
7. **Push room lights** with `scripts/create-room-lights.js` (idempotent, and radii in *scene units*: 10 ft grids get
   half the pixel radius of 5 ft ones). Defaults: warm `#ff9c4a`/`#ffb060`, alpha 0.3–0.35, torch
   animation, dim = 1.4·r, bright = 0.6·r (capped at 40/15 ft).
8. **Check it** at darkness 0, 0.6 and 1 (then restore it): view the scene with no token selected (GM view), then select a token to see its
   vision. Screenshot both.

## Coverage fill (after rooms/sconces)

Room detection leaks on big maps, and the GM still found unlit rooms. Last step: rasterise the floor footprint
(the traced perimeter minus voids), take candidate points on a 50px grid that are ≥45px from any wall, and
greedily add a light at the candidate farthest from all existing lights until every candidate is within 380px
of one (10 ft grid). Also delete auto lights that ended up OUTSIDE the footprint (early grid-sampling put
some on clouds). In Foundry, skip candidates within 300px of any existing light, including the GM's own.

## Atmosphere lights

- Light animation types (V14): flame, torch, revolving, siren, pulse, reactivepulse, chroma, wave, fog, sunburst,
  dome, emanation, hexa, ghost, energy, vortex, witchwave, rainbowswirl, radialrainbow, fairy, grid, starlight,
  smokepatch. There's no "lightning": use **siren** in pale blue/violet with different speeds (3–6), intensity 6.
- Night exterior pass on a garden or estate: lanterns at entrances and stair feet, along the main path, at
  fountains, ponds (blue tint) and bridges, and in groves. Put window glows on the OUTER walls of upper floors
  (`walls:false`, dim ~15). Test at darkness 0.9, then restore.
- GMs want maps brighter than my first guess. Palace room lights ended up at dim 45 / bright 20 (10 ft grid).

## Facts (V14)

- AmbientLight fields: `x, y, elevation, levels, rotation, walls, vision, config, hidden, locked, flags`.
- `scene.environment`: `darknessLevel, darknessLock, globalLight {enabled, alpha, bright, color,
  coloration, luminosity, saturation, contrast, shadows, darkness{min,max}}, cycle, base, dark`.
- `adjustDarknessLevel` behavior: `{mode: 0 override | 1 brighten | 2 darken, modifier: 0–1}`.
- The user may already have placed their own lights. Only ever delete lights tagged `flags.claude.auto`.

## Done so far

- Loomlurch: darkness 0.3, global light (max 0.5), "Interior · Árbol" (darken 0.7, 15 room polygons),
  15 room lights, and 8 night lights (7 exterior doors + a lantern among the tents).
- Bavlorna's Cottage: darkness 0.6, global light (max 0.5), "Interior · Cabaña" per level (darken 0.7,
  surface footprints), 15 room lights (incl. the chandelier), and 18 night lights (5 balcony doors + 13 windows).
- Motherhorn: darkness 0.55, global light (max 0.5), Interior region per level (darken 0.7), 102 sconces,
  the understage bonfire, 2 hall fills, a stage wash, and 4 night lanterns (docks and tower balconies).
- Palace of Heart's Desire: darkness 0.3, rooms dim 45/bright 20, 12 storm 'lightning' lights (siren) on Lower+Upper,
  17 night lanterns in the garden and at the entrances, and 10 window glows on the Upper Floor.
