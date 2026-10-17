// fit-light-radius.js — make each ambient light's dim radius cover most of its room.
// For every light (on every level of the scene), sweep the wall-bounded polygon it can see, sample its area, and raise
// `dim` to the radius covering COVER (95%) of that area, rounded up to 5 ft. Lights are only raised, never lowered;
// open areas (needed radius > MAX_FT) are left alone, as are lights not flagged claude.auto (hand-placed) unless ALL.
// Tiny lights (dim <= minFrom, default 10 ft) are candles and fixtures, not room lights: left alone.
// Usage: set globalThis.__FIT = {scene: id|name, dry: true|false, all: false, minFrom: 10} and run; it views the scene's levels.
async () => {
  const { scene: sid, dry = true, all = false, minFrom = 10 } = globalThis.__FIT ?? {};
  const COVER = 0.95, MAX_FT = 60;
  const scene = game.scenes.get(sid) ?? game.scenes.getName(sid);
  const B = CONFIG.Canvas.polygonBackends.light, ft = scene.grid.distance / scene.grid.size;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const levels = scene.levels.contents.length ? scene.levels.contents : [null];
  const out = [], seen = new Set();
  for (const lv of levels) {
    await scene.view(lv ? { level: lv.id } : {}); await wait(3500);
    for (const l of canvas.lighting.placeables) {
      const d = l.document;
      if (seen.has(d.id) || !l.lightSource || (!all && !d.flags?.claude?.auto) || d.config.dim <= minFrom) continue;
      if (lv && d.levels?.size && !d.levels.has(lv.id)) continue;
      seen.add(d.id);
      const o = { x: d.x, y: d.y, elevation: d.elevation };
      const poly = B.create(o, { type: "light", radius: MAX_FT * 2 / ft, source: l.lightSource });
      const b = poly.getBounds(), st = Math.max(8, Math.min(b.width, b.height) / 60), dist = [];
      for (let x = b.x; x < b.x + b.width; x += st)
        for (let y = b.y; y < b.y + b.height; y += st) if (poly.contains(x, y)) dist.push(Math.hypot(x - o.x, y - o.y));
      if (!dist.length) continue;
      dist.sort((a, c) => a - c);
      const need = Math.ceil(dist[Math.floor(COVER * (dist.length - 1))] * ft / 5) * 5;
      if (need > MAX_FT || need <= d.config.dim) continue;
      out.push({ id: d.id, level: lv?.name, from: d.config.dim, to: need });
      if (!dry) await d.update({ "config.dim": need });
    }
  }
  return { scene: scene.name, changed: out.length, lights: out };
}
