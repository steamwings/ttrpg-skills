// create-ring-walls.js — circular walls around inset circles so an inset (another floor drawn on the
// same image) is visually and physically separate: tokens inside see only the inset, tokens outside
// can't see in, and light doesn't leak. Walls block move/sight/light/sound and are tagged
// flags.claude.ring so re-running replaces them.
// Why walls and not a Region: a Region `restriction` has ONE type (light|darkness|sight|sound|move),
// so it would take 3–4 regions per inset. One ring of walls covers every sense.
// Find the rings with Hough circles (golden border): see references/scene-levels.md.
const SCENE = "Loomlurch";
const RINGS = [[798, 1202, 592], [3194, 3798, 591], [3486, 786, 351]];  // [cx, cy, r] image px (r = inner edge)
const N = 48;                                                          // segments per ring

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX: OX, sceneY: OY } = s.dimensions;
  const lid = s.levels.contents[0].id;
  const docs = [];
  for (const [cx, cy, r] of RINGS) for (let i = 0; i < N; i++) {
    const a0 = 2 * Math.PI * i / N, a1 = 2 * Math.PI * (i + 1) / N;
    docs.push({ c: [cx + r * Math.cos(a0) + OX, cy + r * Math.sin(a0) + OY, cx + r * Math.cos(a1) + OX, cy + r * Math.sin(a1) + OY].map(Math.round),
      levels: [lid], move: 20, sight: 20, light: 20, sound: 20, flags: { claude: { ring: true } } });
  }
  const old = s.walls.filter(w => w.flags?.claude?.ring).map(w => w.id);
  if (old.length) await s.deleteEmbeddedDocuments("Wall", old);
  const c = await s.createEmbeddedDocuments("Wall", docs);
  out = JSON.stringify({ ringWalls: c.length });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
