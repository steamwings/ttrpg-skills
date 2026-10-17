// create-docs.js — create or replace converted Actors/Items in world folders, keeping fixed ids.
// Input BASE/<DOCS>: [{_id, name, type, folder: ["Root", "Sub", ...], img, system, items?: [{name, type, img, system}]}]
// (Item docs have no `items`). Fixed _ids mean re-runs replace in place and every @UUID / token link survives.
// UPLOADS: local files served next to the JSON -> Foundry paths (uploaded once; existing files are kept).
async () => {
  const BASE = "http://localhost:8765";
  const DOCS = "watchers-pool-docs.json";
  const UPLOADS = { "the-watcher.webp": `worlds/${game.world.id}/assets/adversaries/witchlight/the-watcher.webp` };
  const FP = foundry.applications.apps.FilePicker.implementation;
  const out = { created: [], uploaded: [], errors: [] };

  for (const [src, dest] of Object.entries(UPLOADS)) {
    const dir = dest.split("/").slice(0, -1).join("/"), name = dest.split("/").pop();
    const have = (await FP.browse("data", dir)).files.map(f => decodeURIComponent(f.split("/").pop()));
    if (have.includes(name)) continue;
    const blob = await (await fetch(`${BASE}/${src}`)).blob();
    await FP.upload("data", dir, new File([blob], name, { type: blob.type }), {}, { notify: false });
    out.uploaded.push(name);
  }

  const folderPath = async (type, names) => {
    let parent = null;
    for (const name of names) {
      let f = game.folders.find(f => f.type === type && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
      if (!f) f = await Folder.create({ name, type, folder: parent?.id ?? null });
      parent = f;
    }
    return parent?.id ?? null;
  };

  for (const d of await (await fetch(`${BASE}/${DOCS}`)).json()) {
    try {
      const cls = d.items !== undefined || ["adversary", "npc", "environment", "character"].includes(d.type) ? Actor : Item;
      const coll = cls === Actor ? game.actors : game.items;
      const data = { ...d, folder: await folderPath(cls.documentName, d.folder) };
      delete data._key;
      if (cls === Actor) data.prototypeToken = { name: d.name, texture: { src: d.img } };
      await coll.get(d._id)?.delete();
      const doc = await cls.create(data, { keepId: true });
      out.created.push(`${doc.name} (${doc.uuid})`);
    } catch (e) { out.errors.push(`${d.name}: ${e.message}`); }
  }
  return out;
}
