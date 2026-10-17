#!/usr/bin/env python3
"""make_handouts.py SPEC.json OUT_DIR — a handouts journal (one image page per handout) for import-journal.js.

SPEC: {"journal": {"name": "Handouts: Hither"}, "dest": "worlds/<world>/assets/handouts/<adv>",
       "pages": [{"name": "The Watcher", "src": "<url or http://localhost:8765/file>", "caption": "..."}]}
Ids are generated once and written back into SPEC, so re-runs replace in place. Show one handout to the players by
right-clicking its page in the journal's page list -> Show Players.
"""
import json, pathlib, random, string, sys


def rid():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


spec_path, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = json.loads(spec_path.read_text())
out.mkdir(parents=True, exist_ok=True)
spec["journal"].setdefault("_id", rid())
journal, images = {"_id": spec["journal"]["_id"], "name": spec["journal"]["name"], "pages": []}, {}
for i, p in enumerate(spec["pages"]):
    p.setdefault("_id", rid())
    dest = f"{spec['dest'].rstrip('/')}/{p.get('file') or p['src'].split('/')[-1]}"
    images[p["src"]] = dest
    journal["pages"].append({"_id": p["_id"], "name": p["name"], "type": "image", "src": dest, "sort": (i + 1) * 100000,
                             "title": {"show": True, "level": 1}, "image": {"caption": p.get("caption", "")}})
(out / "journal.json").write_text(json.dumps(journal, indent=1, ensure_ascii=False))
(out / "images.json").write_text(json.dumps(images, indent=1))
(out / "tables.json").write_text("[]")
spec_path.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
print(f"{journal['name']} ({journal['_id']}): {len(journal['pages'])} pages")
