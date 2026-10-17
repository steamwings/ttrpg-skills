// build-scene.js — create (or refresh) a single-level scene from scene_from_spec.py's scene.json.
// Reads BASE/<import.json>.scene (default "scene.json"). Uploads `image` to `src` if missing, then sets grid,
// padding, the day/night rule (global light on, darkness max 0.5, starting darkness = mood), and the journal link.
// Replaces only what it owns: walls/lights flagged claude.auto and the region "Interior (auto)".
// Pins and tokens come next: create-area-notes.js and place-tokens.js (their scene id = this scene's id).
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const opt = await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}));
  const S = await (await fetch(`${BASE}/${opt.scene ?? "scene.json"}`)).json();
  const FP = foundry.applications.apps.FilePicker.implementation;
  const out = {};

  // image
  const dir = S.src.split("/").slice(0, -1).join("/"), file = S.src.split("/").pop();
  for (let cur = "", parts = dir.split("/"), i = 0; i < parts.length; i++) {
    cur = cur ? `${cur}/${parts[i]}` : parts[i];
    try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
  }
  if (!(await FP.browse("data", dir)).files.some(f => decodeURIComponent(f.split("/").pop()) === file)) {
    const blob = await (await fetch(`${BASE}/${S.image}`)).blob();
    await FP.upload("data", dir, new File([blob], file, { type: blob.type || "image/webp" }), {}, { notify: false });
    out.uploaded = file;
  }

  // folder + scene
  let parent = null;
  for (const name of S.folder ?? []) {
    let f = game.folders.find(f => f.type === "Scene" && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
    if (!f) f = await Folder.create({ name, type: "Scene", folder: parent?.id ?? null });
    parent = f;
  }
  const base = {
    name: S.name, folder: parent?.id ?? null, width: S.width, height: S.height, padding: 0.05,
    grid: { type: 1, style: "solidLines", thickness: 1, color: "#000000", alpha: 0.15, units: "ft", ...S.grid },
    tokenVision: true, fog: { mode: 1 },
    environment: { darknessLevel: S.darkness ?? 0.3, globalLight: { enabled: S.global !== false, darkness: { max: 0.5 } } },
    journal: S.journal ?? null, journalEntryPage: S.page ?? null,
  };
  let scene = game.scenes.getName(S.name);
  if (!scene) {
    scene = await Scene.create({ ...base, levels: [{ name: S.name, elevation: { bottom: 0, top: 20 }, background: { src: S.src } }] });
    await scene.update({ initialLevel: scene.levels.contents[0].id });
    out.created = scene.id;
  } else {
    await scene.update(base);
    await scene.levels.contents[0].update({ background: { src: S.src } });
    out.updated = scene.id;
  }
  const lv = scene.levels.contents[0];
  const { sceneX: OX, sceneY: OY } = scene.dimensions;

  // walls
  const KIND = { 1: { move: 20, sight: 20, light: 20, sound: 20 }, 2: { move: 20, sight: 20, light: 20, sound: 20, door: 1, ds: 0 },
                 3: { move: 20, sight: 0, light: 0, sound: 10 }, 4: { move: 20, sight: 0, light: 0, sound: 0 },
                 5: { move: 20, sight: 20, light: 20, sound: 20, door: 2, ds: 0 } };   // 5 = secret door
  const own = c => c.filter(d => d.flags?.claude?.auto).map(d => d.id);
  let ids = own(scene.walls); if (ids.length) await scene.deleteEmbeddedDocuments("Wall", ids);
  out.walls = (await scene.createEmbeddedDocuments("Wall", S.walls.map(([x0, y0, x1, y1, k]) => ({
    c: [x0 + OX, y0 + OY, x1 + OX, y1 + OY], levels: [lv.id], flags: { claude: { auto: true } }, ...KIND[k] })))).length;

  // interior darkness region (DARKEN 0.7: no global light inside by day, dark at night)
  ids = scene.regions.filter(r => r.name === "Interior (auto)").map(r => r.id);
  if (ids.length) await scene.deleteEmbeddedDocuments("Region", ids);
  if (S.interiors.length) await scene.createEmbeddedDocuments("Region", [{
    name: "Interior (auto)", color: "#3a2a5a", levels: [lv.id], elevation: { bottom: null, top: null },
    shapes: S.interiors.map(p => ({ type: "polygon", points: p.flatMap(([x, y]) => [x + OX, y + OY]), hole: false })),
    behaviors: [{ type: "adjustDarknessLevel", name: "Interior", system: { mode: 2, modifier: 0.7 } }] }]);

  // lights (always on; warm by default)
  ids = own(scene.lights); if (ids.length) await scene.deleteEmbeddedDocuments("AmbientLight", ids);
  out.lights = (await scene.createEmbeddedDocuments("AmbientLight", S.lights.map(l => ({
    x: l.at[0] + OX, y: l.at[1] + OY, levels: [lv.id], elevation: 5, walls: true, flags: { claude: { auto: true } },
    config: { dim: l.dim ?? 20, bright: l.bright ?? 10, color: l.color ?? "#ffb060", alpha: l.alpha ?? 0.35, luminosity: 0.5,
              attenuation: 0.6, animation: { type: l.anim ?? "torch", speed: 2, intensity: 2 } } })))).length;
  out.id = scene.id;
  return out;
}
