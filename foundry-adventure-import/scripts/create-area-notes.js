// create-area-notes.js — GM-only map pins for keyed areas ("D4"), each opening its own journal page.
// Input BASE/<PINS>: {scene, journal, pins: [{label, name, page, level (Level background file name), x, y}]}
// with x/y in level-image pixels (the scene padding offset is added here).
// The label is drawn into a semi-transparent SVG icon (Note text has no alpha), uploaded once per label.
// Pins are visible only to users who can see the journal: keep the journal at default ownership NONE.
// Idempotent: notes flagged {adventure-import: {area}} on the scene are replaced.
async () => {
  const BASE = "http://localhost:8765";
  const PINS = "cottage-pins.json";
  const ICON_DIR = `worlds/${game.world.id}/assets/notes/areas`;
  const SIZE = 64;                      // icon size in px (grid is 100)
  const FP = foundry.applications.apps.FilePicker.implementation;
  const { scene: sceneId, journal, pins } = await (await fetch(`${BASE}/${PINS}`)).json();
  const scene = game.scenes.get(sceneId);
  const { sceneX, sceneY } = scene.dimensions;

  const svg = label => `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
<circle cx="64" cy="64" r="58" fill="rgb(24,20,16)" fill-opacity="0.5" stroke="rgb(240,210,150)" stroke-opacity="0.65" stroke-width="5"/>
<text x="64" y="64" dy="0.35em" text-anchor="middle" font-family="Signika, Arial, sans-serif" font-weight="700"
 font-size="${label.length > 3 ? 40 : label.length > 2 ? 48 : 56}" fill="rgb(255,240,210)" fill-opacity="0.8">${label}</text></svg>`;

  for (let cur = "", parts = ICON_DIR.split("/"), i = 0; i < parts.length; i++) {
    cur = cur ? `${cur}/${parts[i]}` : parts[i];
    try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
  }
  const have = new Set((await FP.browse("data", ICON_DIR)).files.map(f => decodeURIComponent(f.split("/").pop())));
  for (const label of new Set(pins.map(p => p.label))) {
    const name = `${label.toLowerCase()}.svg`;
    if (have.has(name)) continue;
    await FP.upload("data", ICON_DIR, new File([svg(label)], name, { type: "image/svg+xml" }), {}, { notify: false });
  }

  const levelByFile = Object.fromEntries(scene.levels.contents.map(l =>
    [decodeURIComponent((l.background?.src ?? "").split("/").pop()), l.id]));
  // a Note below/above the viewed level's elevation shows a "-10 ft" badge: sit it on its level's floor
  const floor = Object.fromEntries(scene.levels.contents.map(l => [l.id, l.elevation?.bottom ?? 0]));
  const old = scene.notes.filter(n => n.flags?.["adventure-import"]?.area).map(n => n.id);
  if (old.length) await scene.deleteEmbeddedDocuments("Note", old);
  const data = pins.map(p => ({
    entryId: journal, pageId: p.page, x: p.x + sceneX, y: p.y + sceneY,
    levels: levelByFile[p.level] ? [levelByFile[p.level]] : [], elevation: floor[levelByFile[p.level]] ?? 0,
    texture: { src: `${ICON_DIR}/${p.label.toLowerCase()}.svg` }, iconSize: SIZE,
    text: p.name, fontSize: 24, textAnchor: CONST.TEXT_ANCHOR_POINTS.BOTTOM,
    flags: { "adventure-import": { area: p.label } },
  }));
  const made = await scene.createEmbeddedDocuments("Note", data);
  return { created: made.length, levels: levelByFile, unmatchedLevels: pins.filter(p => !levelByFile[p.level]).map(p => p.label) };
}
