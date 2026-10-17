// move-packs-to-world.js — copy world-compendium content into the world sidebar for play, keeping ids, mirroring
// the compendium folders under a root folder, and rewriting Compendium.world.<prefix>-*.X.<id> links to world
// uuids (X.<id>) so links, Notes and tokens all point at the playable copies. Compendiums are left untouched as backup.
// Idempotent: documents whose id already exists in the world are skipped (world edits win).
async () => {
  const ROOT = "Witchlight";
  const PACKS = [   // pack -> sub folder under ROOT ("" = directly under ROOT)
    ["world.witchlight-adversaries", "Adversaries"],
    ["world.witchlight-npcs", "NPCs"],
    ["world.witchlight-environments", "Environments"],
    ["world.witchlight-items", ""],
  ];
  const LINK = /Compendium\.world\.witchlight-[a-z-]+\.(Actor|Item|JournalEntry|RollTable|Scene|Macro|Playlist)\./g;
  const out = {};

  const folderPath = async (type, names) => {
    let parent = null;
    for (const name of names.filter(Boolean)) {
      let f = game.folders.find(f => f.type === type && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
      if (!f) f = await Folder.create({ name, type, folder: parent?.id ?? null });
      parent = f;
    }
    return parent;
  };

  for (const [packId, sub] of PACKS) {
    const pack = game.packs.get(packId);
    const cls = getDocumentClass(pack.documentName);
    const docs = await pack.getDocuments();
    const res = out[packId] = { created: 0, skipped: 0 };
    const batch = [];
    for (const d of docs) {
      if (pack.documentName === "Actor" ? game.actors.get(d.id) : game.items.get(d.id)) { res.skipped++; continue; }
      const chain = [];
      for (let f = d.folder; f; f = f.folder) chain.unshift(f.name);
      const folder = await folderPath(pack.documentName, [ROOT, sub, ...chain]);
      const data = game.collections.get(pack.documentName).fromCompendium(d, { keepId: true });
      const src = data._stats?.compendiumSource;
      const fixed = JSON.parse(JSON.stringify(data).replace(LINK, "$1."));
      if (src) fixed._stats.compendiumSource = src;
      fixed.folder = folder.id;
      batch.push(fixed);
    }
    if (batch.length) await cls.createDocuments(batch, { keepId: true });
    res.created = batch.length;
  }
  return out;
}
