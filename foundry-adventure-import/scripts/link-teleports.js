// link-teleports.js — teleport regions between stairs/doors on one scene image (floors drawn side by side, or a
// magic door). Input BASE/<import.json>.teleports (default teleports.json): {scene: name|id,
//   pairs: [{name, a: [x, y, w, h], b: [x, y, w, h], oneWay?: true}]} in scene-image px (the padding offset is added).
// Two-way pairs teleport a → b and b → a; oneWay pairs only a → b (b is a plain arrival region). Tokens land in the
// middle of the destination, so a token arriving on stairs doesn't bounce back until it moves again.
// Visible to the GM only. Idempotent: regions flagged adventure-import.teleport are replaced.
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const opt = await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}));
  const { scene: sid, pairs } = await (await fetch(`${BASE}/${opt.teleports ?? "teleports.json"}`)).json();
  const scene = game.scenes.get(sid) ?? game.scenes.getName(sid);
  const { sceneX: ox, sceneY: oy } = scene.dimensions;
  const old = scene.regions.filter(r => r.flags?.["adventure-import"]?.teleport).map(r => r.id);
  if (old.length) await scene.deleteEmbeddedDocuments("Region", old);
  const levels = scene.levels.contents.map(l => l.id);
  const region = (name, [x, y, width, height], color) => ({
    name, color, levels, visibility: 0, highlightMode: "shapes",
    shapes: [{ type: "rectangle", x: ox + x, y: oy + y, width, height }],
    flags: { "adventure-import": { teleport: name } },
  });
  const out = [];
  for (const p of pairs) {
    const [a, b] = await scene.createEmbeddedDocuments("Region", [
      region(`${p.name} (A)`, p.a, "#7a5cff"), region(`${p.name} (B)`, p.b, p.oneWay ? "#999999" : "#7a5cff")]);
    const tp = dest => ({ type: "teleportToken", name: "Teleport", system: { destinations: [dest.uuid], placement: "center", choice: false } });
    await a.createEmbeddedDocuments("RegionBehavior", [tp(b)]);
    if (!p.oneWay) await b.createEmbeddedDocuments("RegionBehavior", [tp(a)]);
    out.push(p.name);
  }
  return out;
}
