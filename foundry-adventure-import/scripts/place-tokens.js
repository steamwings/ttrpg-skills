// place-tokens.js — put the creatures the adventure text places in each area onto the scene, hidden (GM-only)
// until revealed. Input BASE/<import.json>.tokens: plan_tokens.py output {scene, tokens: [{actor, x, y, level, size,
// linked, area}]} (x/y = top-left in level-image px; the scene offset is added here).
// Compendium actors (e.g. SRD adversaries) are imported into the world first (folder SRD_FOLDER, same id) because
// tokens need a world actor. Idempotent: tokens flagged {adventure-import: {area}} on the scene are replaced.
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const SRD_FOLDER = ["Witchlight", "Adversaries", "Daggerheart SRD"];
  const opt = await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}));
  const { scene: sceneId, tokens } = await (await fetch(`${BASE}/${opt.tokens ?? "tokens.json"}`)).json();
  const scene = game.scenes.get(sceneId) ?? game.scenes.getName(sceneId);
  const { sceneX, sceneY } = scene.dimensions;
  const level = Object.fromEntries(scene.levels.contents.map(l =>
    [decodeURIComponent((l.background?.src ?? "").split("/").pop()), l]));
  const out = { imported: [], created: 0, errors: [] };

  const folderPath = async names => {
    let parent = null;
    for (const name of names) {
      let f = game.folders.find(f => f.type === "Actor" && f.name === name && (f.folder?.id ?? null) === (parent?.id ?? null));
      if (!f) f = await Folder.create({ name, type: "Actor", folder: parent?.id ?? null });
      parent = f;
    }
    return parent.id;
  };
  const worldActor = async uuid => {
    if (!uuid.startsWith("Compendium.")) return fromUuid(uuid);
    const id = uuid.split(".").pop();
    if (game.actors.get(id)) return game.actors.get(id);
    const src = await fromUuid(uuid);
    const data = game.actors.fromCompendium(src, { keepId: true });
    data.folder = await folderPath(SRD_FOLDER);
    out.imported.push(src.name);
    return Actor.create(data, { keepId: true });
  };

  const old = scene.tokens.filter(t => t.flags?.["adventure-import"]?.area).map(t => t.id);
  if (old.length) await scene.deleteEmbeddedDocuments("Token", old);
  const data = [];
  for (const t of tokens) {
    try {
      const actor = await worldActor(t.actor);
      const lv = level[t.level];
      const td = await actor.getTokenDocument({
        x: t.x + sceneX, y: t.y + sceneY, hidden: true, width: t.size, height: t.size,
        actorLink: t.linked, elevation: lv?.elevation?.bottom ?? 0, ...(lv ? { level: lv.id } : {}),
        flags: { "adventure-import": { area: t.area } },
      });
      data.push(td.toObject());
    } catch (e) { out.errors.push(`${t.area} ${t.actor}: ${e.message}`); }
  }
  out.created = (await scene.createEmbeddedDocuments("Token", data)).length;
  return out;
}
