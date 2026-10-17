// sync-world-to-packs.js — back up the world's play copies into the world compendiums (the reverse of
// move-packs-to-world.js). The WORLD is the source of truth; run this at the end of a prep session.
// - Same ids (keepId), folders mirrored below each mapping's root, existing pack docs with the same id replaced.
// - Links between synced documents are rewritten World -> Compendium (Actor.X -> Compendium.world.<pack>.Actor.X),
//   so move-packs-to-world.js restores everything exactly (it rewrites them back).
// - Documents that only exist in the pack are left alone. Nothing in the world is changed.
// DRY_RUN = true reports what would happen.
async () => {
  const DRY_RUN = false;
  const ROOT = "Witchlight";
  const SKIP_FOLDERS = ["Daggerheart SRD"];                 // system content copied in for tokens; not ours
  const MAP = [                                             // [document type, sub-folder under ROOT or "*", pack]
    ["Actor", "Adversaries", "world.witchlight-adversaries"],
    ["Actor", "NPCs", "world.witchlight-npcs"],
    ["Actor", "Environments", "world.witchlight-environments"],
    ["Item", "*", "world.witchlight-items"],
    ["JournalEntry", "*", "world.witchlight-journals"],
    ["Scene", "*", "world.witchlight-scenes"],
    ["RollTable", "*", "world.witchlight-tables"],
  ];
  const out = { packs: {}, created: [] };

  // pack for RollTables may not exist yet
  if (!game.packs.get("world.witchlight-tables") && !DRY_RUN) {
    const p = await foundry.documents.collections.CompendiumCollection.createCompendium(
      { label: "Witchlight Tables", name: "witchlight-tables", type: "RollTable" });
    const wf = game.folders.find(f => f.type === "Compendium" && f.name === ROOT);
    if (wf) await p.configure({ folder: wf.id });
    await p.configure({ ownership: { PLAYER: "NONE", ASSISTANT: "OWNER" } });
    out.created.push(p.collection);
  }

  const path = f => { const c = []; for (let x = f; x; x = x.folder) c.unshift(x.name); return c; };
  const plan = [];   // [doc, pack, subPath]
  for (const [type, sub, packId] of MAP) {
    for (const d of game.collections.get(type)) {
      const p = path(d.folder);
      if (p[0] !== ROOT || p.some(n => SKIP_FOLDERS.includes(n))) continue;
      if (sub !== "*" && p[1] !== sub) continue;
      if (sub === "*" && type === "Actor") continue;
      plan.push([d, packId, sub === "*" ? p.slice(1) : p.slice(2)]);
    }
  }
  const where = new Map(plan.map(([d, packId]) => [d.uuid, packId]));
  const LINK = /\b(Actor|Item|JournalEntry|Scene|RollTable)\.([A-Za-z0-9]{16})\b/g;
  const toPack = s => s.replace(LINK, (m, t, id, off, str) => {
    if (off > 0 && str[off - 1] === ".") return m;   // part of a longer uuid (already Compendium.<pack>.Actor.X)
    const p = where.get(`${t}.${id}`);
    return p ? `Compendium.${p}.${t}.${id}` : m;
  });

  for (const [packId] of MAP.map(m => [m[2]])) out.packs[packId] ??= { replaced: 0, added: 0 };
  const byPack = {};
  for (const [d, packId, sub] of plan) (byPack[packId] ??= []).push([d, sub]);
  for (const [packId, items] of Object.entries(byPack)) {
    const pack = game.packs.get(packId);
    if (!pack) { out.packs[packId].error = "pack missing"; continue; }
    if (DRY_RUN) { out.packs[packId].would = items.length; continue; }
    const wasLocked = pack.locked; if (wasLocked) await pack.configure({ locked: false });
    const index = await pack.getIndex();
    const folderIn = async names => {
      let parent = null;
      for (const name of names) {
        let f = pack.folders.find(f => f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
        if (!f) f = await Folder.create({ name, type: pack.documentName, folder: parent?.id ?? null }, { pack: packId });
        parent = f;
      }
      return parent?.id ?? null;
    };
    const datas = [];
    for (const [d, sub] of items) {
      const data = JSON.parse(toPack(JSON.stringify(d.toCompendium(pack, { keepId: true }))));
      data.folder = await folderIn(sub);
      datas.push(data);
    }
    const existing = datas.map(x => x._id).filter(id => index.has(id));
    if (existing.length) await pack.documentClass.deleteDocuments(existing, { pack: packId });
    await pack.documentClass.createDocuments(datas, { pack: packId, keepId: true });
    out.packs[packId].replaced = existing.length;
    out.packs[packId].added = datas.length - existing.length;
    if (wasLocked) await pack.configure({ locked: true });
  }
  return out;
}
