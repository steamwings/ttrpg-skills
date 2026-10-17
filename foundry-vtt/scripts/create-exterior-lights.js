// create-exterior-lights.js — night-only exterior lights so "Transition to Darkness" looks right:
// lanterns outside exterior doors, warm glow outside windows, and hand-placed lanterns (camps, stalls).
// Points come from exterior_openings.py ({KEY:[[x,y,kind]]}); kind 2 door, 3 window, 4 hand-placed lantern.
// Each light has config.darkness {min: 0.45, max: 1}: off by day, on from dusk. Idempotent (flags.claude.exterior).
const SCENE = "Bavlorna's Cottage";
const POINTS = { /* "Second Floor": [[348,40,3], [140,946,2], ...] — keys are Level names */ };
const NIGHT = { min: 0.45, max: 1 };

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX: OX, sceneY: OY } = s.dimensions;
  const sq = s.grid.distance;                                  // ft per square (5 or 10)
  const torch = { type: "torch", speed: 2, intensity: 2 };
  const CFG = {
    2: { dim: sq * 2, bright: sq * 0.75, color: "#ffc070", alpha: 0.4, luminosity: 0.5, attenuation: 0.5, animation: torch },  // door lantern
    3: { dim: sq * 1.5, bright: 0, color: "#ffb060", alpha: 0.25, luminosity: 0.4, attenuation: 0.7, animation: { type: null } }, // window glow
    4: { dim: sq * 3, bright: sq, color: "#ffc070", alpha: 0.4, luminosity: 0.5, attenuation: 0.5, animation: torch },          // camp lantern
  };
  const old = s.lights.filter(l => l.flags?.claude?.exterior).map(l => l.id);
  if (old.length) await s.deleteEmbeddedDocuments("AmbientLight", old);
  const docs = [];
  for (const [ln, pts] of Object.entries(POINTS)) {
    const lv = s.levels.getName(ln);
    if (!lv) throw new Error(`level not found: ${ln}`);
    for (const [x, y, k] of pts) docs.push({ x: x + OX, y: y + OY, levels: [lv.id], elevation: (lv.elevation.bottom ?? 0) + 5,
      walls: true, flags: { claude: { auto: true, exterior: true } }, config: { ...CFG[k], darkness: NIGHT } });
  }
  const c = await s.createEmbeddedDocuments("AmbientLight", docs);
  out = JSON.stringify({ exterior: c.length });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
