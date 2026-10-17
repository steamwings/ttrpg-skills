// create-stair.js — a two-way stair/ladder between Scene Levels (V14 "changeLevel" region).
// Rect is in IMAGE px (the level texture); the padding offset is added here.
// After adding/moving stairs, re-run create-surfaces.js so the floor surfaces get matching holes.
const SCENE = "Bavlorna's Cottage";
const NAME = "Escalera · Baja ↔ Segunda";
const LEVELS = ["Ground Floor", "Second Floor"];   // EVERY level the stair connects
const RECT = [600, 300, 100, 100];                  // x, y, w, h in image px (1 square = grid size)

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX, sceneY } = s.dimensions;
  const ids = LEVELS.map(n => { const l = s.levels.getName(n); if (!l) throw new Error(`level not found: ${n}`); return l.id; });
  const old = s.regions.getName(NAME);
  if (old) await old.delete();
  const [r] = await s.createEmbeddedDocuments("Region", [{
    name: NAME,
    color: "#e0a257",
    levels: ids,
    // Unbounded elevation: the `levels` field already limits where it applies. A band like
    // 0–10 (topInclusive false) silently breaks going DOWN: a token standing on the upper
    // floor (elevation 10) is outside the band and the region never fires.
    elevation: { bottom: null, top: null },
    shapes: [{ type: "rectangle", x: RECT[0] + sceneX, y: RECT[1] + sceneY, width: RECT[2], height: RECT[3], rotation: 0, hole: false }],
    behaviors: [{ type: "changeLevel", name: "Change Level", system: { movementActions: [] } }], // [] = any movement action
  }]);
  out = JSON.stringify({ created: r.id, name: r.name, levels: Array.from(r.levels) });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
