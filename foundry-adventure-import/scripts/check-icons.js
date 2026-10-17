// check-icons.js — which core icon paths in BASE/icons-check.json don't exist, with same-folder candidates
// (guessed icon names are often wrong; run before create-docs.js).
async () => {
  const BASE = globalThis.__IMPORT_BASE ?? "http://localhost:8765";
  const want = await (await fetch(`${BASE}/icons-check.json`)).json();
  const FP = foundry.applications.apps.FilePicker.implementation;
  const out = {};
  for (const p of want) {
    if ((await fetch(p, { method: "HEAD" })).status === 200) continue;
    const dir = p.split("/").slice(0, -1).join("/"), words = p.split("/").pop().replace(".webp", "").split("-");
    try {
      const files = (await FP.browse("public", dir)).files.map(f => f.split("/").pop());
      out[p] = files.filter(f => words.some(w => w.length > 3 && f.includes(w))).slice(0, 10);
    } catch { out[p] = "no such folder"; }
  }
  return out;
}
