#!/usr/bin/env python3
"""build_links.py JOURNAL.json PREFIX SPEC.json OUT.json — actor-links.json for link-actors.js from readable targets.

SPEC: [{"actor": "Actor.<id>", "name": "...", "links": ["Page title", "Page title > Heading text", ...]}]
Targets are resolved against the converted journal (page ids + Foundry heading slugs); labels read "PREFIX › target".
Fails loudly on a target that doesn't exist, so a re-split journal can't leave stale links behind.
"""
import json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fivetools_to_foundry import slugify_heading, plain

journal, prefix, spec, out = sys.argv[1:5]
j = json.load(open(journal))
base = f"JournalEntry.{j['_id']}.JournalEntryPage."
pages = {p["name"]: p["_id"] for p in j["pages"]}
heads = {}
for p in j["pages"]:
    for _, h in re.findall(r"<h(\d)>(.*?)</h\1>", p.get("text", {}).get("content", "")):
        t = plain(re.sub(r"@UUID\[[^\]]*\]\{([^}]*)\}", r"\1", h))
        heads.setdefault((p["name"], t), slugify_heading(t))
res = []
for a in json.load(open(spec)):
    links = []
    for target in a["links"]:
        page, _, head = (x.strip() for x in target.partition(">"))
        if page not in pages: sys.exit(f"no page {page!r} for {a['name']}")
        if head and (page, head) not in heads: sys.exit(f"no heading {head!r} on {page!r} for {a['name']}")
        links.append({"uuid": base + pages[page] + (f"#{heads[(page, head)]}" if head else ""),
                      "label": f"{prefix} › {head or page}"})
    res.append({"actor": a["actor"], "name": a["name"], "links": links})
json.dump({"journal": j["_id"], "actors": res}, open(out, "w"), indent=1, ensure_ascii=False)
print(f"{len(res)} actors -> {out}")
