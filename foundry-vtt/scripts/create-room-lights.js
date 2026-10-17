// create-room-lights.js — the lighting pass every map gets during prep.
// 1) scene mood: darkness level (+ optional global light for outdoor maps)
// 2) optional "Interior" region with adjustDarknessLevel so global light stops at the walls
// 3) one warm, wall-clipped light per room (rooms from rooms_from_walls.py or detect_rooms.py)
// Idempotent: replaces lights tagged flags.claude.auto and the region named INTERIOR_NAME.
// Lights sit at elevation (level bottom + 5) and are tagged with their level.
const SCENE = "Loomlurch";
// Always enable global light with max 0.5 so "Transition to Darkness/Daylight" works on every map; the
// darkness value is just the starting mood (0.3 afternoon, 0.6 dusk, 1 night).
const MOOD = { darkness: 0.3, globalLight: true, globalMaxDarkness: 0.5 };
const INTERIOR_NAME = "Interior · Árbol";      // null = no interior region (all-indoor maps don't need one)
const INTERIOR_DARKNESS = 0.7;                 // DARKEN mode: day 0 -> 0.7 (> globalMaxDarkness, so no global light inside), night 1 -> 1
// ROOMS: [levelName, x, y, rPx, polyOrNull]  (image px; r = equivalent radius of the room)
const ROOMS = [ /* paste, e.g. ["Loomlurch", 2676, 1109, 178, [2718,913, ...]] */ ];
const LIGHT = { color: "#ff9c4a", alpha: 0.35, luminosity: 0.5, attenuation: 0.6,
                animation: { type: "torch", speed: 2, intensity: 2 }, dimMul: 1.4, brightMul: 0.6, maxDim: 40, maxBright: 15 };

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX: OX, sceneY: OY } = s.dimensions;
  const ftPerPx = s.grid.distance / s.grid.size;       // respects 5 ft vs 10 ft grids
  await s.update({ "environment.darknessLevel": MOOD.darkness,
                   "environment.globalLight.enabled": MOOD.globalLight,
                   "environment.globalLight.darkness.max": MOOD.globalMaxDarkness ?? 1 });
  const lvl = n => { const l = s.levels.getName(n); if (!l) throw new Error(`level not found: ${n}`); return l; };
  if (INTERIOR_NAME) {
    const old = s.regions.filter(r => r.name === INTERIOR_NAME).map(r => r.id);
    if (old.length) await s.deleteEmbeddedDocuments("Region", old);
    const byLevel = {};
    for (const [ln, , , , poly] of ROOMS) if (poly) (byLevel[ln] ??= []).push(poly);
    await s.createEmbeddedDocuments("Region", Object.entries(byLevel).map(([ln, polys]) => ({
      name: INTERIOR_NAME, color: "#3a2a5a", levels: [lvl(ln).id], elevation: { bottom: null, top: null },
      shapes: polys.map(p => ({ type: "polygon", points: p.map((v, i) => v + (i % 2 ? OY : OX)), hole: false })),
      behaviors: [{ type: "adjustDarknessLevel", name: "Interior oscuro", system: { mode: 2, modifier: INTERIOR_DARKNESS } }],  // mode 0 override (static! breaks day/night), 1 brighten, 2 darken
    })));
  }
  const oldL = s.lights.filter(l => l.flags?.claude?.auto && !l.flags?.claude?.exterior).map(l => l.id);
  if (oldL.length) await s.deleteEmbeddedDocuments("AmbientLight", oldL);
  const docs = ROOMS.map(([ln, x, y, r]) => { const l = lvl(ln), rf = r * ftPerPx; return {
    x: x + OX, y: y + OY, levels: [l.id], elevation: (l.elevation.bottom ?? 0) + 5, walls: true,
    flags: { claude: { auto: true } },
    config: { dim: Math.min(LIGHT.maxDim, Math.round(rf * LIGHT.dimMul)), bright: Math.min(LIGHT.maxBright, Math.round(rf * LIGHT.brightMul)),
              color: LIGHT.color, alpha: LIGHT.alpha, luminosity: LIGHT.luminosity, attenuation: LIGHT.attenuation, animation: LIGHT.animation } }; });
  const c = await s.createEmbeddedDocuments("AmbientLight", docs);
  out = JSON.stringify({ lights: c.length, darkness: s.environment.darknessLevel });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
