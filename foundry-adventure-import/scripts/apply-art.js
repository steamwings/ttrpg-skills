// apply-art.js — set official art on world actors from book_art.py's plan.json (served at BASE/<art>/).
// Uploads portraits/tokens to worlds/<world>/<dir>/{portraits,tokens}, sets actor.img on every non-character actor
// with that name, and, when the plan has a token, the prototype token and the tokens already placed on scenes.
// import.json: {"art": "art", "artDir": "assets/art"}. Re-runnable (uploads overwrite).
// Generated actors are recreated by create-docs.js: give them the same art in their generator (img/token) too.
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const opt = await fetch(`${BASE}/import.json`).then(r => r.json()).catch(() => ({}));
  const SRC = `${BASE}/${opt.art ?? "art"}`;
  const ROOT = `worlds/${game.world.id}/${opt.artDir ?? "assets/art"}`;
  const FP = foundry.applications.apps.FilePicker.implementation;
  const plan = await (await fetch(`${SRC}/plan.json`)).json();
  for (const d of [ROOT, `${ROOT}/portraits`, `${ROOT}/tokens`]) {
    let cur = "";
    for (const part of d.split("/")) {
      cur = cur ? `${cur}/${part}` : part;
      try { await FP.browse("data", cur); } catch { await FP.createDirectory("data", cur); }
    }
  }
  const done = {};
  const upload = async rel => done[rel] ??= (async () => {
    const [dir, file] = rel.split("/");
    const blob = await (await fetch(`${SRC}/${file}`)).blob();
    return (await FP.upload("data", `${ROOT}/${dir}`, new File([blob], file, { type: "image/webp" }), {}, { notify: false })).path;
  })();
  const log = [];
  for (const [name, e] of Object.entries(plan)) {
    const actors = game.actors.filter(a => a.name === name && a.type !== "character");
    if (!actors.length) { log.push(`missing ${name}`); continue; }
    const img = await upload(e.img), tok = e.token ? await upload(e.token) : null;
    for (const a of actors) {
      await a.update({ img, ...(tok ? { "prototypeToken.texture.src": tok } : {}) });
      if (tok) for (const s of game.scenes) {
        const ts = s.tokens.filter(t => t.actorId === a.id).map(t => ({ _id: t.id, "texture.src": tok }));
        if (ts.length) await s.updateEmbeddedDocuments("Token", ts);
      }
    }
    log.push(`${name} x${actors.length}${tok ? " +token" : ""}`);
  }
  return log;
}
