#!/usr/bin/env python3
"""pdf_to_fivetools.py PDF OUT.json [--skip 1,2,12] [--title "Name"] [--known names.json]

Rebuild the structure of a Homebrewery/GMBinder "PHB style" PDF (DMsGuild supplements) as a 5etools-like chapter,
so fivetools_to_foundry.py can convert it like book text. Font roles (this template):
  Mr.EavesSmallCaps   headings: >=20pt section (page), 15-16pt h2, 12-13pt h3; 17pt = stat block name
  Bookmania-*         body text (Bold -> creature link candidate, Italic -> {@i}, BoldItalic at line start -> run-in head)
  ScalaSans* (dark)   read-aloud boxes; a run that starts with a ScalaSans-Bold 10pt title is a sidebar (inset);
                      lines split into wide-gapped spans are table rows
  ScalaSans* (red)    stat block body (with the 8pt italic type line and dark bold-italic trait names)
  NouvelleVague-*     in-world letters/stories -> quote
  ignored: white text (map labels, cover), page headers/footers (ScalySans, y > 803), credit/ad colours.
Also writes OUT.statblocks.json (raw 5e stat block text by name) for converting the creatures by hand.
Inline mechanics are re-tagged ({@dc}, {@skill}, {@dice}, {@condition}) so the 5e -> Daggerheart rules apply.
"""
import argparse, json, re, sys
import pymupdf

SKILLS = ["Athletics", "Acrobatics", "Sleight of Hand", "Stealth", "Arcana", "History", "Investigation", "Nature",
          "Religion", "Medicine", "Animal Handling", "Insight", "Perception", "Survival", "Deception",
          "Intimidation", "Performance", "Persuasion"]
CONDS = ["prone", "restrained", "grappled", "invisible", "stunned", "paralyzed", "blinded", "frightened",
         "charmed", "incapacitated", "unconscious", "poisoned", "deafened", "petrified"]


def is_red(c):
    r, g, b = c >> 16 & 255, c >> 8 & 255, c & 255
    return r > 50 and r > g * 1.5 and r > b * 1.3


def role(s, y):
    f, size, c = s["font"], s["size"], s["color"]
    if c == 16777215 or y > 803 or f.startswith("ScalySans") or f.startswith("Zatanna"):
        return "skip"
    if f.startswith("Mr.Eaves"):
        if 16.5 <= size <= 17.5: return "sbname"
        return "h1" if size >= 20 else "h2" if size >= 14.5 else "h3"
    if f.startswith("Bookmania"): return "body"
    if f.startswith("NouvelleVague"): return "letter"
    if f.startswith("ScalaSans"):
        if size >= 9.5 and "Bold" in f and not is_red(c):
            r, g, b = c >> 16 & 255, c >> 8 & 255, c & 255
            return "boxtitle" if max(r, g, b) < 80 else "skip"   # grey/blue = credits & ads
        if is_red(c): return "sb"
        if size < 8.3 and "Ita" in f: return "sbtype"
        return "box"
    return "body"


def styled(spans, first_line):
    out = []
    for i, s in enumerate(spans):
        t = s["text"]
        if not t.strip():
            out.append(t); continue
        f = s["font"]
        lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S).groups()
        bold, ital = "Bold" in f, "Ita" in f
        if bold and ital and first_line and i == 0:
            core = "{@b {@i " + core + "}}"
        elif bold and not ital and f.startswith("Bookmania"):
            core = "@@BOLD[" + core + "]"       # resolved later: creature link or bold
        elif ital and not bold:
            core = "{@i " + core + "}"
        elif bold:
            core = "{@b " + core + "}"
        out.append(lead + core + trail)
    return "".join(out)


def tag_mechanics(s):
    s = re.sub(r"\bDC (\d+)\b", r"{@dc \1}", s)
    s = re.sub(r"(\{@dc \d+\} )(strength|dexterity|constitution|intelligence|wisdom|charisma)\b", lambda m: m.group(1) + m.group(2).title(), s)
    alt = "|".join(SKILLS)
    s = re.sub(r"\((" + alt + r") or (" + alt + r")\)", r"({@skill \1} or {@skill \2})", s)
    for sk in SKILLS:
        s = re.sub(r"\((" + sk + r")\)", r"({@skill \1})", s)
        s = re.sub(r"\(\{@skill (" + sk + r")\} or (" + "|".join(SKILLS) + r")\)", r"({@skill \1} or {@skill \2})", s)
    s = re.sub(r"(?<![{\w])(\d*d\d+(?:\s*[+−-]\s*\d+)?)(?![\w}])", r"{@dice \1}", s)
    for c in CONDS:
        s = re.sub(r"(?<![{@\w])\b(" + c + r")\b(?![^{]*\})", r"{@condition \1}", s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("out")
    ap.add_argument("--skip", default=""); ap.add_argument("--title", default=None)
    ap.add_argument("--known", default=None, help="JSON list of creature names to link when bold in body text")
    ap.add_argument("--order", choices=["columns", "stream"], default="columns",
                    help="columns: left column then right, top to bottom (default); stream: PDF content order")
    ap.add_argument("--move", action="append", default=[], help='"Child>Parent": move a named entry to the end of another section (fixes sidebar reading order)')
    a = ap.parse_args()
    skip = {int(x) for x in a.skip.split(",") if x}
    known = {n.lower() for n in json.load(open(a.known))} if a.known else set()
    doc = pymupdf.open(a.pdf)

    # 1. lines with roles, in reading order (block stream order is column order in these PDFs)
    lines = []
    for pn, pg in enumerate(doc, 1):
        if pn in skip: continue
        mid = pg.rect.width / 2
        blocks = [b for b in pg.get_text("dict")["blocks"] if b["type"] == 0]
        if a.order == "columns":   # 2-column PHB layout: left column, then right column, each top to bottom
            blocks.sort(key=lambda b: (b["bbox"][0] >= mid - 10, round(b["bbox"][1])))
        for b in blocks:
            if b["type"] != 0: continue
            for li, l in enumerate(b["lines"]):
                spans = [s for s in l["spans"] if s["text"]]
                if not "".join(s["text"] for s in spans).strip(): continue
                main_span = next(s for s in spans if s["text"].strip())
                r = role(main_span, l["bbox"][1])
                if r == "skip": continue
                gaps = [spans[i + 1]["bbox"][0] - spans[i]["bbox"][2] for i in range(len(spans) - 1)]
                lines.append({"role": r, "spans": spans, "block": (pn, b["number"]), "first": li == 0,
                              "x": l["bbox"][0], "y": l["bbox"][1], "x1": l["bbox"][2], "size": main_span["size"],
                              "cells": max(gaps, default=0) > 18 and r == "box"})

    # column right edges, for telling verse (short lines) from wrapped prose
    col_right = {}
    for l in lines:
        k = (l["block"][0], l["x"] > 297)
        col_right[k] = max(col_right.get(k, 0), l["x1"])
    for l in lines:
        l["short"] = col_right[(l["block"][0], l["x"] > 297)] - l["x1"] > 30

    # 2. group into elements
    root = {"type": "section", "name": a.title or "Supplement", "entries": []}
    stack = [(0, root)]
    statblocks, n_id = {}, [0]

    def nid():
        n_id[0] += 1; return f"p{n_id[0]}"

    def push(e): stack[-1][1]["entries"].append(e)

    def text_of(ls, style=True):
        t = ""
        for k, l in enumerate(ls):
            seg = styled(l["spans"], l["first"] or k == 0) if style else "".join(s["text"] for s in l["spans"])
            seg = re.sub(r"[ \t]+", " ", seg).strip()
            prev = ls[k - 1] if k else None
            verse = (prev and prev["role"] in ("box", "letter") and prev["short"]
                     and re.match(r"^[\"“‘'A-Z]", seg) and re.search(r"[,.!?;:\"”’']$", t))
            if t.endswith("-") and seg[:1].islower(): t += seg
            elif verse: t += "\n" + seg
            else: t = (t + " " + seg).strip()
        return t

    i = 0
    while i < len(lines):
        l = lines[i]; r = l["role"]
        if r in ("h1", "h2", "h3"):
            lvl = {"h1": 1, "h2": 2, "h3": 3}[r]
            j = i + 1
            while j < len(lines) and lines[j]["role"] == r and lines[j]["block"] == l["block"] and abs(lines[j]["size"] - l["size"]) < .2:
                j += 1
            name = dedupe(text_of(lines[i:j], style=False))
            nxt = lines[j]["role"] if j < len(lines) else None
            if nxt in ("sb", "sbtype"):          # a stat block whose name uses a heading size
                l = dict(l, role="sbname"); lines[i] = l
                lines[i]["_name"] = name; lines[i + 1:j] = []
                continue
            e = {"type": "section" if lvl == 1 else "entries", "name": name, "id": nid(), "entries": []}
            while stack[-1][0] >= lvl: stack.pop()
            push(e); stack.append((lvl, e)); i = j; continue
        if r == "sbname":
            j = i + 1   # trait/action text is dark ScalaSans too; stop at body text, a heading or a big jump
            while j < len(lines) and lines[j]["role"] in ("sb", "sbtype", "box"):
                if lines[j]["block"][0] == lines[j - 1]["block"][0] and lines[j]["y"] - lines[j - 1]["y"] > 40 \
                        and lines[j]["x"] - lines[j - 1]["x"] < 100: break
                j += 1
            name = l.get("_name") or dedupe(text_of([l], style=False))
            k = i + 1
            while k < j and lines[k]["role"] == "sbname": k += 1      # shadow copy of the name
            statblocks[name] = "\n".join("".join(s["text"] for s in x["spans"]) for x in lines[k:j])
            if not (stack[-1][1]["entries"] and stack[-1][1]["entries"][-1] == {"type": "statblock", "name": name}):
                push({"type": "statblock", "name": name})
            i = j; continue
        if r in ("box", "boxtitle", "letter", "sb", "sbtype"):
            j = i
            while j < len(lines) and lines[j]["role"] == lines[i]["role"] or (j < len(lines) and lines[j]["role"] == "box" and lines[i]["role"] == "boxtitle"):
                j += 1
            run = lines[i:j]
            if r == "boxtitle":
                k = 1
                while k < len(run) and run[k]["role"] == "boxtitle": k += 1
                title = text_of(run[:k], style=False)
                push({"type": "inset", "name": title, "entries": paragraphs(run[k:], text_of)})
            elif r == "letter":
                push({"type": "quote", "entries": paragraphs(run, text_of)})
            elif sum(x["cells"] for x in run) >= 2:
                push(table(run))
            else:
                push({"type": "insetReadaloud", "entries": paragraphs(run, text_of)})
            i = j; continue
        # body: paragraphs / list items until a non-body line
        j = i
        while j < len(lines) and lines[j]["role"] == "body": j += 1
        for p in paragraphs(lines[i:j], text_of, body=True):
            push(p)
        i = j

    # 3. finish strings: mechanics tags, bold creature names
    def fin(s):
        s = tag_mechanics(s)
        return re.sub(r"@@BOLD\[([^\]]*)\]", lambda m: ("{@creature " + m.group(1).strip() + "}") if m.group(1).strip().lower().rstrip("s") in known or m.group(1).strip().lower() in known else "{@b " + m.group(1) + "}", s)

    def walk(e):
        if isinstance(e, str): return fin(e)
        if isinstance(e, dict):
            for k in ("entries", "items"):
                if k in e: e[k] = [walk(x) for x in e[k]]
            if "rows" in e: e["rows"] = [[walk(c) for c in r] for r in e["rows"]]
            if "entry" in e: e["entry"] = walk(e["entry"])
        return e

    walk(root)
    apply_moves(root, a.move)
    json.dump({"data": [root]}, open(a.out, "w"), indent=1, ensure_ascii=False)
    json.dump(statblocks, open(a.out.replace(".json", ".statblocks.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{a.out}: {len(root['entries'])} sections, {len(statblocks)} stat blocks: {', '.join(statblocks)}")


def dedupe(s):
    """Headings drawn twice (shadow) extract as "Name Name"."""
    w = s.split()
    h = len(w) // 2
    return " ".join(w[:h]) if len(w) % 2 == 0 and w[:h] == w[h:] else s


def apply_moves(root, moves):
    def find(e, name, parent=None):
        for k, x in enumerate(e.get("entries", [])):
            if isinstance(x, dict):
                if x.get("name") == name: return e, k
                r = find(x, name)
                if r: return r
        return None
    for mv in moves:
        child, parent = mv.split(">")
        src = find(root, child); dst = find(root, parent)
        if not src or not dst: print(f"move: not found {mv}", file=sys.stderr); continue
        sec, k = src
        node = sec["entries"].pop(k)
        dsec, dk = find(root, parent)
        dsec["entries"][dk]["entries"].append(node)


def paragraphs(ls, text_of, body=False):
    """Split a run of lines into paragraphs (new block, bullet, or run-in bold-italic head) and bullet lists."""
    paras, cur = [], []
    for k, l in enumerate(ls):
        t0 = l["spans"][0]["text"].lstrip()
        if body:
            starts = l["first"] or t0.startswith("•") or "BoldIta" in l["spans"][0]["font"]
        else:   # boxes: one block per line, so split on a blank-line gap instead
            prev = ls[k - 1] if k else None
            starts = prev is not None and (l["y"] - prev["y"] > l["size"] * 2.1 or l["y"] < prev["y"])
        if cur and starts:
            paras.append(cur); cur = []
        cur.append(l)
    if cur: paras.append(cur)
    # drop cap: a lone big letter starts the next paragraph
    merged = []
    for p in paras:
        if merged and len(merged[-1]) == 1 and len("".join(s["text"] for s in merged[-1][0]["spans"]).strip()) == 1:
            p = [dict(p[0], spans=merged.pop()[0]["spans"] + p[0]["spans"])] + p[1:]
        merged.append(p)
    paras = merged
    out, items = [], []
    for p in paras:
        t = text_of(p)
        # a paragraph that continues in the next column/page: previous one has no closing punctuation
        if out and isinstance(out[-1], str) and not items and not re.search(r"[.!?:\"”’\]}]$", out[-1]) \
                and re.match(r"^[a-z(0-9]", t):
            out[-1] = out[-1] + " " + t
            continue
        if t.startswith("•"):
            items.append(t.lstrip("•  ").strip()); continue
        if items: out.append({"type": "list", "items": items}); items = []
        out.append(t)
    if items: out.append({"type": "list", "items": items})
    return out


def table(run):
    rows = []
    for l in run:
        cells, cur = [], ""
        for k, s in enumerate(l["spans"]):
            if k and s["bbox"][0] - l["spans"][k - 1]["bbox"][2] > 18:
                cells.append(cur.strip()); cur = ""
            cur += s["text"]
        cells.append(cur.strip())
        if rows and len(cells) == 1:      # wrapped continuation of the last cell
            rows[-1][-1] += " " + cells[0]
        else:
            rows.append(cells)
    head = rows[0] if rows and all(len(c) < 40 for c in rows[0]) else None
    return {"type": "table", "colLabels": head or [], "rows": rows[1:] if head else rows}


if __name__ == "__main__":
    main()
