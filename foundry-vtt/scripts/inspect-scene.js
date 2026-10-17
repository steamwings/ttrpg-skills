// inspect-scene.js — one-shot summary of a V14 scene: dimensions/padding, levels, regions, walls, tokens.
// Run via javascript_tool. Sets are converted with Array.from (JSON.stringify(Set) === "{}").
const SCENE = "Bavlorna's Cottage";

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}. Scenes: ${game.scenes.map(x => x.name).join(" | ")}`);
  const d = s.dimensions;
  const lname = Object.fromEntries(s.levels.map(l => [l.id, l.name]));
  out = JSON.stringify({
    scene: s.name, id: s.id,
    dims: { sceneX: d.sceneX, sceneY: d.sceneY, w: d.sceneWidth, h: d.sceneHeight, grid: s.grid.size, padding: s.padding },
    levels: s.levels.map(l => ({ id: l.id, name: l.name, elev: l.elevation, bg: l.background?.src })),
    regions: s.regions.map(r => ({
      id: r.id, name: r.name,
      levels: Array.from(r.levels ?? []).map(id => lname[id] ?? id),
      elev: [r.elevation.bottom, r.elevation.top],
      behaviors: r.behaviors.map(b => b.type),
      shapes: r.shapes.map(x => [x.type, x.x, x.y, x.width, x.height, x.hole ? "hole" : ""].filter(v => v !== "")),
    })),
    walls: s.walls.size,
    wallsPerLevel: Object.fromEntries(s.levels.map(l => [l.name, s.walls.filter(w => w.levels.has(l.id)).length])),
    tokens: s.tokens.map(t => ({ name: t.name, x: t.x, y: t.y, elev: t.elevation, level: lname[t.level] ?? t.level })),
  });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
