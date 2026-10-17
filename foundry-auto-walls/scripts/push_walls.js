// push_walls.js — create Foundry V14 Wall documents from detect_walls.py output.
// Run through Claude in Chrome's javascript_tool on the Foundry /game tab (GM logged in).
// Fill in SCENE, LEVEL_NAMES and WALLS (paste walls.json). ~4 KB of JSON per call is fine;
// for bigger payloads, accumulate over several calls:  window.__W = Object.assign(window.__W||{}, {...})
// and then set  const WALLS = window.__W;
//
// Coordinates in WALLS are IMAGE pixels; the scene padding offset (sceneX/sceneY) is added here.
// REPLACE=true deletes existing walls on the targeted levels first, so re-running is idempotent.

const SCENE = "Bavlorna's Cottage";
const LEVEL_NAMES = { L1: "Ground Floor", L2: "Second Floor", L3: "Third Floor" };
const WALLS = /* paste walls.json here */ {};
const REPLACE = true;

// Sense values: 0 NONE, 10 LIMITED, 20 NORMAL (CONST.WALL_SENSE_TYPES). Door 1 = DOOR, ds 0 = CLOSED.
const KIND = {
  1: { move: 20, sight: 20, light: 20, sound: 20 },                  // wall
  2: { move: 20, sight: 20, light: 20, sound: 20, door: 1, ds: 0 },  // door (closed)
  3: { move: 20, sight: 0, light: 0, sound: 10 },                    // window: blocks movement, see-through
  4: { move: 20, sight: 0, light: 0, sound: 0 },                     // edge (sky/cliff): blocks movement only
};

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX, sceneY } = s.dimensions;
  const lv = {};
  for (const [k, name] of Object.entries(LEVEL_NAMES)) {
    const l = s.levels.getName(name);
    if (!l) throw new Error(`level not found: ${name}`);
    lv[k] = l.id;
  }
  let deleted = 0;
  if (REPLACE) {
    const target = new Set(Object.keys(WALLS).map(k => lv[k]));
    const ids = s.walls.filter(w => [...w.levels].some(id => target.has(id))).map(w => w.id);
    if (ids.length) await s.deleteEmbeddedDocuments("Wall", ids);
    deleted = ids.length;
  }
  const docs = [];
  for (const [k, segs] of Object.entries(WALLS)) {
    for (const [x0, y0, x1, y1, kind] of segs) {
      docs.push({ c: [x0 + sceneX, y0 + sceneY, x1 + sceneX, y1 + sceneY], levels: [lv[k]], ...KIND[kind] });
    }
  }
  const created = await s.createEmbeddedDocuments("Wall", docs);
  out = JSON.stringify({ deleted, created: created.length, doors: created.filter(w => w.door).length, total: s.walls.size });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
