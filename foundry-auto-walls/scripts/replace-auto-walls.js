// Replace Claude's auto walls on some levels with a walls.json uploaded through #claude-upload.
// Only walls flagged flags.claude.auto are deleted, so walls the GM drew by hand survive.
// 1) create/show the hidden input (see foundry-vtt/scripts/upload-files.js), file_upload the JSON to it
// 2) paste this (fire-and-forget), then read JSON.stringify(window.__push) in a second call.
// walls.json: {"L1": [[x0,y0,x1,y1,kind], ...], ...} in IMAGE px; kind 1 wall, 2 door, 3 window, 4 edge.
const LEVELS = { L1: "Lower Floor", L2: "Upper Floor" };   // json key -> Level name
window.__push = { stage: "start" };
(async () => { try {
  const s = canvas.scene; const inp = document.getElementById("claude-upload");
  const W = JSON.parse(await inp.files[0].text()); inp.style.display = "none";
  const OX = s.dimensions.sceneX, OY = s.dimensions.sceneY;
  const LV = Object.fromEntries(Object.entries(LEVELS).map(([k, n]) => [k, s.levels.getName(n).id]));
  const ids = new Set(Object.values(LV));
  const del = s.walls.filter(w => w.flags?.claude?.auto && Array.from(w.levels).some(id => ids.has(id))).map(w => w.id);
  window.__push.stage = "deleting " + del.length;
  for (let i = 0; i < del.length; i += 1000) await s.deleteEmbeddedDocuments("Wall", del.slice(i, i + 1000));
  const docs = [];
  for (const k of Object.keys(LV)) for (const [x0, y0, x1, y1, kind] of (W[k] || [])) {
    if (x0 === x1 && y0 === y1) continue;
    const d = { c: [x0 + OX, y0 + OY, x1 + OX, y1 + OY], levels: [LV[k]], flags: { claude: { auto: true } } };
    if (kind === 2) Object.assign(d, { door: 1, ds: 0 });
    else if (kind === 3) Object.assign(d, { sight: 0, light: 0, sound: 10 });
    else if (kind === 4) Object.assign(d, { sight: 0, light: 0, sound: 0 });
    docs.push(d);
  }
  window.__push.stage = "creating " + docs.length;
  for (let i = 0; i < docs.length; i += 1000) await s.createEmbeddedDocuments("Wall", docs.slice(i, i + 1000));
  // keep stair squares walkable: drop non-door auto walls inside changeLevel / teleport regions
  const stairs = s.regions.filter(r => r.behaviors.some(b => ["changeLevel", "teleportToken"].includes(b.type)));
  const rm = [];
  for (const w of s.walls) {
    if (!w.flags?.claude?.auto || w.door) continue;
    const mx = (w.c[0] + w.c[2]) / 2, my = (w.c[1] + w.c[3]) / 2;
    for (const r of stairs) {
      if (!Array.from(r.levels).some(id => w.levels.has(id))) continue;
      if (r.shapes.some(sh => !sh.hole && sh.type === "rectangle" && mx >= sh.x && mx <= sh.x + sh.width && my >= sh.y && my <= sh.y + sh.height)) { rm.push(w.id); break; }
    }
  }
  if (rm.length) await s.deleteEmbeddedDocuments("Wall", rm);
  window.__push = { stage: "done", deleted: del.length, created: docs.length, stairCleared: rm.length };
} catch (e) { window.__push = { stage: "error", msg: e.message }; } })();
"fired";
