// link-actors.js — append "📖 <journal section>" links to actor descriptions (idempotent per journal).
// Input BASE/actor-links.json: {journal: "<JournalEntry id>", actors: [{actor: uuid, links: [{uuid, label}]}]}
// The link paragraph is replaced on re-run: any <p> starting with 📖 that links into the same journal is removed first.
// Keep descriptions short — the long text lives in the (GM-only) journal page the link opens.
async () => {
  const BASE = "http://localhost:8765";
  const FIELD = "system.description";
  const { journal, actors } = await (await fetch(`${BASE}/actor-links.json`)).json();
  const out = { updated: [], failed: [] };
  for (const a of actors) {
    try {
      const doc = await fromUuid(a.actor);
      let html = foundry.utils.getProperty(doc, FIELD) ?? "";
      html = html.replace(new RegExp(`<p>📖[^]*?JournalEntry\\.${journal}[^]*?</p>`, "g"), "");
      const links = a.links.map(l => `@UUID[${l.uuid}]{${l.label}}`).join(" · ");
      await doc.update({ [FIELD]: `${html}<p>📖 ${links}</p>` });
      out.updated.push(doc.name);
    } catch (e) { out.failed.push(`${a.name ?? a.actor}: ${e.message}`); }
  }
  return out;
}
