// create-teleport-stairs.js — stairs between places drawn on the SAME image (inset circles
// showing upper floors, "unfolded" levels) using teleportToken regions instead of Scene Levels.
// Each pair = 2 stair regions + 2 landing regions. A stair teleports to the landing next to the
// OTHER stair (never straight onto the other stair, or it would fire again on arrival).
// choice:true -> the player gets "Do you want to teleport X to <landing>?" (Teleport / Don't Teleport),
// the same confirm-style UX as changeLevel. Idempotent: deletes regions named "Escalera · " / "Llegada · ".
// Coordinates: image px [x, y] of the top-left of a 100x100 square; padding offset is added here.
const SCENE = "Loomlurch";
const PAIRS = [   // up = stair on the main map, dn = stair in the inset; *L = landing square beside it
  { n: "Torre NE",        up: [2620, 900],  upL: [2640, 1020], dn: [3440, 610],  dnL: [3450, 720] },
  { n: "Torre central",   up: [2230, 2090], upL: [2130, 2010], dn: [820, 1360],  dnL: [720, 1290] },
  { n: "Torre del telar", up: [1580, 2690], upL: [1680, 2730], dn: [3190, 3840], dnL: [3300, 3880] },
  { n: "Huerto de calabazas", up: [1570, 2240], upL: [1620, 2090], dn: [3190, 3290], dnL: [3090, 3580] },  // outdoor stair by the pumpkins -> lower-right inset
];

let out;
try {
  const s = game.scenes.getName(SCENE);
  if (!s) throw new Error(`scene not found: ${SCENE}`);
  const { sceneX: OX, sceneY: OY } = s.dimensions;
  const lid = s.levels.contents[0].id;              // single-level scene; adapt for multi-level
  const R = (x, y) => ({ type: "rectangle", x: x + OX, y: y + OY, width: 100, height: 100, rotation: 0, hole: false });
  const base = { levels: [lid], elevation: { bottom: null, top: null } };
  const old = s.regions.filter(r => /^(Escalera|Llegada) · /.test(r.name)).map(r => r.id);
  if (old.length) await s.deleteEmbeddedDocuments("Region", old);
  const L = await s.createEmbeddedDocuments("Region", PAIRS.flatMap(p => [
    { ...base, name: `Llegada · ${p.n} (abajo)`, color: "#8fbc8f", shapes: [R(...p.upL)], behaviors: [] },
    { ...base, name: `Llegada · ${p.n} (arriba)`, color: "#8fbc8f", shapes: [R(...p.dnL)], behaviors: [] },
  ]));
  const uuid = Object.fromEntries(L.map(r => [r.name, r.uuid]));
  const tp = dest => [{ type: "teleportToken", name: "Escalera",
    system: { destinations: [dest], placement: "center", snap: true, choice: true } }];  // placement: random|center|relative
  const S = await s.createEmbeddedDocuments("Region", PAIRS.flatMap(p => [
    { ...base, name: `Escalera · ${p.n} ↑ subir`, color: "#e0a257", shapes: [R(...p.up)], behaviors: tp(uuid[`Llegada · ${p.n} (arriba)`]) },
    { ...base, name: `Escalera · ${p.n} ↓ bajar`, color: "#e0a257", shapes: [R(...p.dn)], behaviors: tp(uuid[`Llegada · ${p.n} (abajo)`]) },
  ]));
  out = JSON.stringify({ stairs: S.length, landings: L.length });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
