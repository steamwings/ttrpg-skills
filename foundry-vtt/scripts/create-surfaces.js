// create-surfaces.js — (re)create one "defineSurface" region per level (the solid floor that
// blocks sight/light/sound/movement between levels), with a HOLE over every changeLevel region
// tagged on that level. Without the holes the full-floor surface sits on top of the stairs and
// the GM cannot click/edit them. Idempotent: deletes "<Level> — surface" regions first.
// FOOTPRINT = building outline per level in IMAGE px [x, y, w, h] (a rectangle is fine).
const SCENE = "Bavlorna's Cottage";
const FOOTPRINT = {
  "Ground Floor": [190, 290, 1720, 1310],
  "Second Floor": [90, 90, 2000, 1520],
  "Third Floor": [679, 371, 918, 855],
};

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX, sceneY } = s.dimensions;
  const docs = [];
  for (const [name, [x, y, w, h]] of Object.entries(FOOTPRINT)) {
    const lvl = s.levels.getName(name);
    if (!lvl) throw new Error(`level not found: ${name}`);
    const holes = s.regions
      .filter(r => r.levels.has(lvl.id) && r.behaviors.some(b => b.type === "changeLevel"))
      .flatMap(r => r.shapes.map(sh => ({ ...sh.toObject(), hole: true })));
    docs.push({
      name: `${name} — surface`,
      color: "#4a7a8c",
      levels: [lvl.id],
      elevation: { bottom: null, top: null },
      visibility: 0,
      shapes: [{ type: "rectangle", x: x + sceneX, y: y + sceneY, width: w, height: h, rotation: 0, hole: false }, ...holes],
      behaviors: [{
        type: "defineSurface", name: "Surface",
        system: { placement: "bottom", light: true, move: true, sight: true, sound: true, occlusion: true, exposure: false, culling: false },
      }],
    });
  }
  const oldIds = s.regions.filter(r => docs.some(d => d.name === r.name)).map(r => r.id);
  if (oldIds.length) await s.deleteEmbeddedDocuments("Region", oldIds);
  const created = await s.createEmbeddedDocuments("Region", docs);
  out = JSON.stringify(created.map(r => ({ name: r.name, holes: r.shapes.filter(x => x.hole).length })));
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
