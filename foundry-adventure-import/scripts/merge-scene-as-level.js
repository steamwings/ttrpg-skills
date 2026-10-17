// merge-scene-as-level.js — fold a connected map (a cellar, a den under a building) into another scene as a V14 Level.
// Input BASE/<import.json>.merge (default merge.json): {target: sceneId, source: sceneId, name: "Level name",
//   elevation: {bottom, top}, image: "served file" (the source map pasted onto a canvas the size of the target's level
//   image, offset so the two staircases line up — snap the offset to the grid), offset: [x, y] (that paste offset, px),
//   stairs: [{name, rect: [x, y, w, h]}] (level-image px; a changeLevel region on both levels), dest: "data path",
//   deleteSource: false}.
// Copies the source scene's notes, tokens and regions (offset, on the new level, at its floor elevation), and walls and
// lights (restricted to the new level). Idempotent: everything it made is flagged adventure-import.merged = name.
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const opt = await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}));
  const M = await (await fetch(`${BASE}/${opt.merge ?? "merge.json"}`)).json();
  const T = game.scenes.get(M.target), S = game.scenes.get(M.source);
  const FP = foundry.applications.apps.FilePicker.implementation;
  const dir = M.dest.split("/").slice(0, -1).join("/"), file = M.dest.split("/").pop();
  const blob = await (await fetch(`${BASE}/${M.image}`)).blob();
  const src = (await FP.upload("data", dir, new File([blob], file, { type: blob.type || "image/webp" }), {}, { notify: false })).path;
  let lv = T.levels.find(l => l.name === M.name);
  if (lv) await lv.update({ elevation: M.elevation, background: { src } });
  else [lv] = await T.createEmbeddedDocuments("Level", [{ name: M.name, elevation: M.elevation, background: { src } }]);
  const floor = M.elevation.bottom, F = { "adventure-import": { merged: M.name } };
  const mine = d => d.flags?.["adventure-import"]?.merged === M.name;
  for (const [coll, cls] of [[T.notes, "Note"], [T.tokens, "Token"], [T.regions, "Region"], [T.walls, "Wall"], [T.lights, "AmbientLight"]]) {
    const ids = coll.filter(mine).map(d => d.id);
    if (ids.length) await T.deleteEmbeddedDocuments(cls, ids);
  }
  const [ox, oy] = M.offset, { sceneX: tx, sceneY: ty } = T.dimensions, { sceneX: sx, sceneY: sy } = S.dimensions;
  const X = x => x - sx + tx + ox, Y = y => y - sy + ty + oy;
  const strip = d => { const o = d.toObject(); delete o._id; o.flags = { ...o.flags, ...F }; return o; };
  const out = {};
  out.notes = (await T.createEmbeddedDocuments("Note", S.notes.map(n => ({ ...strip(n), x: X(n.x), y: Y(n.y), levels: [lv.id], elevation: floor })))).length;
  out.tokens = (await T.createEmbeddedDocuments("Token", S.tokens.map(t => ({ ...strip(t), x: X(t.x), y: Y(t.y), level: lv.id, elevation: floor })))).length;
  out.regions = (await T.createEmbeddedDocuments("Region", S.regions.map(r => {
    const o = strip(r);
    o.shapes = o.shapes.map(s => s.points ? { ...s, points: s.points.map((v, i) => i % 2 ? Y(v) : X(v)) } : { ...s, x: X(s.x), y: Y(s.y) });
    o.behaviors.forEach(b => delete b._id);
    return { ...o, name: `${o.name} · ${M.name}`, levels: [lv.id] };
  }))).length;
  out.walls = (await T.createEmbeddedDocuments("Wall", S.walls.map(w => {
    const o = strip(w); const [a, b, c, d] = o.c; return { ...o, c: [X(a), Y(b), X(c), Y(d)], levels: [lv.id] };
  }))).length;
  out.lights = (await T.createEmbeddedDocuments("AmbientLight", S.lights.map(l => ({ ...strip(l), x: X(l.x), y: Y(l.y), levels: [lv.id], elevation: floor + 5 })))).length;
  const below = T.levels.find(l => l.id !== lv.id && (l.elevation.bottom === M.elevation.top || l.elevation.top === M.elevation.bottom)) ?? T.levels.find(l => l.id !== lv.id);
  out.stairs = (await T.createEmbeddedDocuments("Region", (M.stairs ?? []).map(s => ({
    name: s.name, color: "#e0a257", levels: [below.id, lv.id], visibility: 2, flags: F,
    shapes: [{ type: "rectangle", x: tx + s.rect[0], y: ty + s.rect[1], width: s.rect[2], height: s.rect[3] }],
    behaviors: [{ type: "changeLevel", name: "Change Level", system: { movementActions: [] } }],
  })))).length;
  if (M.deleteSource) { await S.delete(); out.deleted = S.name; }
  return out;
}
