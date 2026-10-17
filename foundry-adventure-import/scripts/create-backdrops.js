// create-backdrops.js — "theater of the mind" scenes from mood art: no grid, no vision, no fog.
// For moments without tokens, or the beat just before a battle map. Input BASE/<backdrops> (import.json key,
// default backdrops.json): {root: ["Adventure", "Backdrops"], dir: "assets/backdrops",
//   items: [{region, file, name, page (JournalEntryPage uuid), map (battle-map Scene id|null), w, h, sort}]}.
// Each scene goes in folder root/region, players see `name` (navName), the GM sees "BG · name".
// The scene links the journal page, and gets a GM-only pin for it; the page gets a 🎬 line linking the
// backdrop (and the battle map). Idempotent: scenes are matched by flag adventure-import.backdrop = file.
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const KEY = (await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}))).backdrops ?? "backdrops.json";
  const cfg = await (await fetch(`${BASE}/${KEY}`)).json();
  const FP = foundry.applications.apps.FilePicker.implementation;
  const DIR = `worlds/${game.world.id}/${cfg.dir ?? "assets/backdrops"}`;
  for (let cur = "", parts = DIR.split("/"), i = 0; i < parts.length; i++) {
    cur = cur ? `${cur}/${parts[i]}` : parts[i];
    try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
  }
  const folderPath = async names => {
    let parent = null;
    for (const name of names) {
      let f = game.folders.find(f => f.type === "Scene" && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
      if (!f) f = await Folder.create({ name, type: "Scene", folder: parent?.id ?? null });
      parent = f;
    }
    return parent;
  };
  const log = [];
  for (const it of cfg.items) {
    const blob = await (await fetch(`${BASE}/${cfg.src ?? "bg"}/${it.file}`)).blob();
    const src = (await FP.upload("data", DIR, new File([blob], it.file, { type: blob.type }), {}, { notify: false })).path;
    const folder = await folderPath([...(cfg.root ?? ["Backdrops"]), it.region]);
    const page = fromUuidSync(it.page);
    const base = {
      name: `BG · ${it.name}`, navName: it.name, folder: folder.id, width: it.w, height: it.h, padding: 0,
      backgroundColor: "#000000", grid: { type: 0 }, tokenVision: false, fog: { exploration: false },
      environment: { darknessLevel: 0, globalLight: { enabled: true } }, navigation: false, sort: it.sort ?? 0,
      initial: { x: it.w / 2, y: it.h / 2, scale: Math.min(1, 1000 / it.h) },
      journal: page?.parent?.id ?? null, journalEntryPage: page?.id ?? null,
      flags: { "adventure-import": { backdrop: it.file } },
    };
    let scene = game.scenes.find(s => s.flags?.["adventure-import"]?.backdrop === it.file);
    if (!scene) {
      scene = await Scene.create({ ...base, levels: [{ name: it.name, elevation: { bottom: 0, top: 20 }, background: { src } }] });
      await scene.update({ initialLevel: scene.levels.contents[0].id });
    } else {
      await scene.update(base);
      await scene.levels.contents[0].update({ background: { src } });
    }
    // GM-only pin (the journal is ownership NONE) in the top-left corner
    const old = scene.notes.filter(n => n.flags?.["adventure-import"]?.backdrop).map(n => n.id);
    if (old.length) await scene.deleteEmbeddedDocuments("Note", old);
    if (page) await scene.createEmbeddedDocuments("Note", [{
      entryId: page.parent.id, pageId: page.id, x: 80, y: 80, iconSize: 64, levels: [scene.levels.contents[0].id],
      texture: { src: "icons/svg/book.svg" }, text: page.name, fontSize: 24,
      flags: { "adventure-import": { backdrop: it.file } },
    }]);
    // 🎬 line at the top of the journal page
    if (page?.type === "text") {
      const map = it.map ? game.scenes.get(it.map) : null;
      const line = `<p data-backdrop="${it.file}">🎬 @UUID[${scene.uuid}]{Backdrop: ${it.name}}` +
        (map ? ` · 🗺️ @UUID[${map.uuid}]{Map: ${map.name}}` : "") + `</p>`;
      const html = (page.text.content ?? "").replace(new RegExp(`<p data-backdrop="${it.file}">.*?</p>`), "");
      await page.update({ "text.content": line + html });
    }
    log.push(`${it.region}/${it.name}${page ? "" : " (no page!)"}`);
  }
  return log;
}
