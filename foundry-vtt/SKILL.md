---
name: foundry-vtt
description: Build and fix Foundry VTT V14 worlds by running JS in the user's Foundry browser tab. Covers scenes, Scene Levels (multi-floor), stair and surface regions, walls, and asset uploads. Use for any Foundry build or migration work, including Daggerheart worlds.
---

# Foundry VTT (V14) from Claude

## How to connect

Two transports. Both run JS in a logged-in `/game` page; the scripts here work with either.

- **Playwright MCP** (when the container can reach the server, e.g. `http://host.docker.internal:30000/game`
  for a Foundry on the Docker host): `browser_navigate` to `/game`, then `browser_evaluate` with
  `() => { ... }`. Return objects directly (no `JSON.stringify` needed), and async functions are fine.
  Exceptions come back with their message. Console output lands in `.playwright-mcp/console-*.log`.
  Uploads: `browser_file_upload` on the file input (see `scripts/upload-files.js`).
- **Claude in Chrome** (when the server is only reachable from the user's own browser):
  `tabs_context_mcp` → find the `/game` tab → `javascript_tool` on it. Rules below.
- Either way, the session must be a GM (`game.user.isGM`; role 3 Assistant GM is enough for world
  content) in the right world. Check `game.world.title` before writing anything.
- Setup-level actions (installing or updating systems and modules, creating worlds from Setup, deleting
  files) cannot be done from inside a world. Ask the user to do them.

## Browser JS rules (learned the hard way; the first three are Claude in Chrome only)

- **Any uncaught exception returns only `Tool "javascript_tool" failed in the extension`**, with
  no message. Always wrap the code: `let out; try { ... out = JSON.stringify(x) } catch(e) { out = "ERROR: "+e.message } out;`.
  Common cause: `collection.getName(...)` returned `undefined` because the user renamed or deleted it.
- **Long awaits fail** (for example `await new Promise(r=>setTimeout(r,2500))` combined with token moves). Fire the
  action in one call and check the result in the next.
- **Large outputs are truncated.** Query in pieces.
- **Token x/y updates are wall-constrained in V14.** `token.update({x,y})` from one side of a wall to the
  other silently does nothing. To teleport a test token, delete it and recreate it where you want it.
  To test movement, use `token.move([...waypoints])` along the real path (through doors and necks).
- **Sets:** `JSON.stringify(new Set([...]))` is `{}`. Use `Array.from(doc.levels)`.
- **The user is working live in the same world.** Re-inspect before editing, because they rename or
  delete regions between turns. Make scripts idempotent (replace by name).
- Batch clicks and screenshots with `browser_batch`. Screenshot after visible changes
  (`save_to_disk: true` gives a file you can send with SendUserFile).

## Scene Levels essentials (read references/scene-levels.md before building a multi-floor scene)

- One Scene, several **Levels** (name, elevation band, own **background texture**).
- A Level texture **fills the whole scene**: no x/y/size. So every floor image must be pre-cropped
  to the **same canvas size, with the grid phase at 0**, and floors must be aligned to each other.
  Use the `map-prep` skill.
- Canvas coords = image px + `scene.dimensions.sceneX/sceneY` (the padding offset). All scripts
  here take image px and add the offset themselves.
- **Stairs** = a Region with the `changeLevel` behavior, tagged (`levels`) on **every** level it
  connects, with **unbounded elevation**. Players walk onto it and Foundry asks
  "Move to Second Floor?" (Move Down / Don't Move). Nothing happens automatically.
- **Surfaces** = a `defineSurface` Region per level (the solid floor), with **holes over the stairs**,
  or the GM cannot select the stairs underneath. `scripts/create-surfaces.js` rebuilds them.
- **Walls** have `levels` too. See the `foundry-auto-walls` skill.

## Scripts (fill the constants at the top, run in the `/game` page)

| script | does |
|---|---|
| `scripts/create-scene.js` | new scene from grid-aligned level images (single- or multi-level), grid size and distance, initial level |
| `scripts/inspect-scene.js` | levels, regions (levels, elevation, behaviors, shapes), walls per level, tokens |
| `scripts/create-stair.js` | changeLevel region between N levels (idempotent by name) |
| `scripts/create-surfaces.js` | per-level floor surfaces with stair holes (idempotent; re-run after stair changes) |
| `scripts/create-teleport-stairs.js` | stairs between places drawn on the same image (insets), with teleportToken + landings |
| `scripts/create-ring-walls.js` | circular walls around inset circles to separate vision, light and movement |
| `scripts/rooms_from_walls.py` | rooms (light position, radius, polygon) from a walls.json |
| `scripts/create-room-lights.js` | lighting pass: mood/darkness, interior darkness region, one warm light per room |
| `scripts/find_sconces.py` | light markers drawn on the map (red sconce dots) → light positions |
| `scripts/exterior_openings.py` | exterior doors and windows → points just outside, for night lights |
| `scripts/create-exterior-lights.js` | night-only lanterns and window glow (darkness 0.45–1) |
| `scripts/move-packs-to-world.js` | copy world-compendium actors/items into world folders (same ids), rewrite compendium links |
| `scripts/upload-files.js` | upload workspace files into `Data/` through a hidden file input and `FilePicker.upload` |

## Grid distance comes from the map

Read the map's scale legend. Bavlorna's Cottage uses 5 ft squares, but **Loomlurch uses 10 ft**
("1 square = 10 feet"). Set `grid.distance` to match, or ranges and movement will be wrong.

## Lighting is part of every map

After the walls, always do the lighting pass in `references/lighting.md`.

## Test like a player

Put a token on a stair and move it off and back on. Use `tokenDoc.move([{x,y}])` without awaiting,
then screenshot to catch the confirm dialog, click it, and read `token.level` / `token.elevation`.
Check both directions (up **and** down).

## Daggerheart system (Foundryborne) notes

- v2.7.4 on core V14 once installed incompletely: `ENOENT` for `templates/.../effects.hbs` and
  `tooltipTags.hbs` crashed the character sheet before the class `<select>` was wired up, so
  "can't pick a class" was **not** user error. Fix: reinstall or update the system from Setup → Game
  Systems. Check the console (`read_console_messages` or the Playwright console log, pattern `ENOENT|Error`) whenever a sheet
  misbehaves.
- D&D 5e compendium actors do **not** port (the system is tagged dnd5e). Rebuild adversaries in
  Daggerheart and use old name lists only as a checklist. Scenes (without a system tag) port fine.

## Conventions

See `references/conventions.md` (world layout, asset folders, file names, compendium folders).
