// import-journal.js — upload a converted chapter's images and (re)create its JournalEntry in a compendium.
// Run in the Foundry /game page (Playwright browser_evaluate, or wrap for javascript_tool).
// Inputs come from fivetools_to_foundry.py output, served by serve_cors.py:
//   BASE/journal.json  JournalEntry data with fixed _ids (keepId) so re-runs replace in place
//   BASE/images.json   {sourceUrl: "worlds/<world>/assets/..."}; existing files are skipped
async () => {
  const BASE = "http://localhost:8765";            // serve_cors.py
  const PACK = "world.witchlight-journals";        // target compendium
  const FOLDER = "Book";                           // compendium folder for the journal ("" = none)
  const out = { uploaded: [], skipped: [], failed: [] };

  const FP = foundry.applications.apps.FilePicker.implementation;
  const ensureDir = async path => {
    let cur = "";
    for (const part of path.split("/")) {
      cur = cur ? `${cur}/${part}` : part;
      try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
    }
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

  // 2. journal (replace by id)
  const data = await (await fetch(`${BASE}/journal.json`)).json();
  const pack = game.packs.get(PACK);
  if (FOLDER) {
    let f = pack.folders.find(f => f.name === FOLDER);
    if (!f) f = await Folder.create({ name: FOLDER, type: "JournalEntry" }, { pack: PACK });
    data.folder = f.id;
  }
  const old = await pack.getDocument(data._id);
  if (old) await old.delete();
  const doc = await JournalEntry.create(data, { pack: PACK, keepId: true });
  out.journal = { uuid: doc.uuid, pages: doc.pages.size };
  return out;
}
