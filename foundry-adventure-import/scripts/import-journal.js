// import-journal.js — upload a converted chapter's images and (re)create its RollTables and JournalEntry.
// Run in the Foundry /game page (Playwright browser_evaluate, or wrap for javascript_tool).
// Inputs come from fivetools_to_foundry.py output, served by serve_cors.py:
//   BASE/journal.json  JournalEntry data with fixed _ids (keepId) so re-runs replace in place
//   BASE/tables.json   RollTable data (fixed _ids), embedded in the pages with @Embed[RollTable.<id> rollable]
//   BASE/images.json   {sourceUrl: "worlds/<world>/assets/..."}; existing files are skipped
// Target: the world (PACK = "") under folder paths, or a compendium (PACK = "world.<pack>", FOLDER_PATH[last] used).
async () => {
  const BASE = "http://localhost:8765";
  // optional BASE/import.json overrides these: {"pack": "", "journalFolder": [...], "tableFolder": [...]}
  const opt = await fetch(`${BASE}/import.json`).then(r => r.ok ? r.json() : {}).catch(() => ({}));
  const PACK = opt.pack ?? "";                      // "" = world sidebar
  const JOURNAL_FOLDER = opt.journalFolder ?? ["Witchlight", "Book"];
  const TABLE_FOLDER = opt.tableFolder ?? ["Witchlight", "Hither"];
  const out = { uploaded: [], skipped: [], failed: [] };

  const FP = foundry.applications.apps.FilePicker.implementation;
  const ensureDir = async path => {
    let cur = "";
    for (const part of path.split("/")) {
      cur = cur ? `${cur}/${part}` : part;
      try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
    }
  };
  const folderPath = async (type, names) => {
    const coll = PACK ? game.packs.get(PACK).folders : game.folders;
    let parent = null;
    for (const name of (PACK ? names.slice(-1) : names)) {
      let f = coll.find(f => f.type === type && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
      if (!f) f = await Folder.create({ name, type, folder: parent?.id ?? null }, PACK ? { pack: PACK } : {});
      parent = f;
    }
    return parent?.id ?? null;
  };
  const replace = async (cls, data) => {   // delete + create keeps ids stable and drops stale pages/results
    const old = PACK ? await game.packs.get(PACK).getDocument(data._id)
      : game.collections.get(cls.documentName).get(data._id);
    if (old) await old.delete();
    return cls.create(data, { keepId: true, ...(PACK ? { pack: PACK } : {}) });
  };

  // 1. images
  const images = await (await fetch(`${BASE}/images.json`)).json();
  const dirs = [...new Set(Object.values(images).map(p => p.split("/").slice(0, -1).join("/")))];
  const existing = new Set();
  for (const d of dirs) {
    await ensureDir(d);
    (await FP.browse("data", d)).files.forEach(f => existing.add(decodeURIComponent(f)));
  }
  for (const [src, dest] of Object.entries(images)) {
    if (existing.has(dest)) { out.skipped.push(dest); continue; }
    try {
      const blob = await (await fetch(src)).blob();
      const name = dest.split("/").pop();
      const file = new File([blob], name, { type: blob.type || "image/webp" });
      await FP.upload("data", dest.split("/").slice(0, -1).join("/"), file, {}, { notify: false });
      out.uploaded.push(name);
    } catch (e) { out.failed.push(`${dest}: ${e.message}`); }
  }

  // 2. roll tables
  const tables = await (await fetch(`${BASE}/tables.json`)).json().catch(() => []);
  const tFolder = tables.length ? await folderPath("RollTable", TABLE_FOLDER) : null;
  out.tables = [];
  for (const t of tables) out.tables.push((await replace(RollTable, { ...t, folder: tFolder })).name);

  // 3. journal
  const data = await (await fetch(`${BASE}/journal.json`)).json();
  data.folder = await folderPath("JournalEntry", JOURNAL_FOLDER);
  const doc = await replace(JournalEntry, data);
  out.journal = { uuid: doc.uuid, pages: doc.pages.size };
  return out;
}
