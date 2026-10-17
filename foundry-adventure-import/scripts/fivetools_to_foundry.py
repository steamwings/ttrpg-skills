#!/usr/bin/env python3
"""fivetools_to_foundry.py — turn one chapter of a 5etools adventure JSON into Foundry JournalEntry data,
converting D&D 5e mechanics to Daggerheart and linking creatures/items to existing compendium documents.

usage: fivetools_to_foundry.py CONFIG.json OUT_DIR

CONFIG (see ../examples/adventure-config.example.json):
  adventure       path to the 5etools adventure-<id>.json (adventureData[0].data = chapters)
  chapter         chapter index in data[]
  journal         {name, id?, folder?}  (id is generated and written back if missing, so re-runs replace)
  split_words     split a top-level section into one page per named child when it has more words (3000)
  pages           optional explicit plan: [{"title":..., "ids":[5etools entry ids]}] (overrides the split rule)
  index           foundry-index.json from the Foundry tab: [{pack, doc, name, type, uuid}]
  pack_priority   packs searched first for name matches (world packs before system ones)
  aliases         {"5etools name (lowercase)": "Foundry name" | null}  null = known, no stat block yet
  item_aliases    same for items
  img_base        URL prefix for 5etools image paths (raw 5etools-img repo)
  img_dest        Foundry path the images get uploaded to (e.g. worlds/<world>/assets/journals/<adv>/<chapter>)
  page_links      {"page title": [uuid, ...]}  shown at the top of a page (e.g. the location's Environment actor)
  overrides       [[find, replace], ...] applied to the rendered HTML of every page (manual mechanic fixes)

OUT_DIR gets: journal.json (create data, keepId), images.json (url -> Foundry path), anchors.json
(entry id / creature -> page uuid#anchor, for actor back-links), review.md (5e leftovers to fix by hand).
"""
import html, json, pathlib, random, re, string, sys, unicodedata
from collections import defaultdict

# ---------- 5e -> Daggerheart ----------

SKILL_TRAIT = {
    "athletics": "Strength", "acrobatics": "Agility", "sleight of hand": "Finesse", "stealth": "Finesse",
    "arcana": "Knowledge", "history": "Knowledge", "investigation": "Knowledge", "nature": "Knowledge",
    "religion": "Knowledge", "medicine": "Knowledge", "animal handling": "Instinct", "insight": "Instinct",
    "perception": "Instinct", "survival": "Instinct", "deception": "Presence", "intimidation": "Presence",
    "performance": "Presence", "persuasion": "Presence",
}
ABILITY_TRAIT = {"strength": "Strength", "dexterity": "Agility", "constitution": "Strength",
                 "intelligence": "Knowledge", "wisdom": "Instinct", "charisma": "Presence"}
FINESSE_HINT = re.compile(r"thieves' tools|lock|pick|sleight|delicate|disarm", re.I)
PHYSICAL = {"bludgeoning", "piercing", "slashing"}
# 5e condition -> (shown text, Daggerheart condition or None)
CONDITIONS = {"prone": "Vulnerable", "restrained": "Restrained", "grappled": "Restrained",
              "invisible": "Hidden", "stunned": "Vulnerable", "paralyzed": "Vulnerable", "blinded": "Vulnerable"}
LEFTOVER = re.compile(r"hit points?|saving throw|armor class|\bAC\b|proficien|spell slot|\bXP\b|experience points|"
                      r"\bto hit\b|\b\d+(st|nd|rd|th)-level|\bcheck\b|\bspeed\b|temporary hit|darkvision", re.I)


def an(word):
    return "an" if word[0].lower() in "aeiou" else "a"


def range_name(feet):
    feet = int(feet)
    return ("Melee" if feet <= 5 else "Very Close" if feet <= 10 else "Close" if feet <= 30
            else "Far" if feet <= 100 else "Very Far")


def trait_for(ability, skills, sentence):
    traits = []
    for s in skills:
        t = SKILL_TRAIT.get(s.lower())
        if t and t not in traits: traits.append(t)
    if not traits:
        t = ABILITY_TRAIT[ability.lower()]
        if ability.lower() == "dexterity" and FINESSE_HINT.search(sentence): t = "Finesse"
        traits = [t]
    return " or ".join(traits)


ABIL = r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
SKILLS = r"(?: \((\{@skill [^}]+\}(?: or \{@skill [^}]+\})*)\))?"
RX_CHECK = re.compile(r"(?:\b(a|an) )?\{@dc (\d+)\} " + ABIL + SKILLS + r" (group )?check")
RX_PLAIN_CHECK = re.compile(ABIL + SKILLS + r" check(s)?\b")   # no DC: "disadvantage on Dexterity (Stealth) checks"
RX_SAVE = re.compile(r"(?:\b(a|an) )?\{@dc (\d+)\} " + ABIL + r" saving throw")
RX_SAVE_DC = re.compile(r"\(save \{@dc (\d+)\}\)")
RX_DMG = re.compile(r"\b\d+ \(\{@dice ([^}]+)\}\) (\w+) damage")
RX_WITHIN = re.compile(r"\bwithin (\d+) feet\b")


def dh_hp(m):
    """5e object/creature hit points -> a Daggerheart-sized HP count (about 1 HP per 6 hp, at least 1)."""
    return str(max(1, round(int(m) / 6)))


GENERIC = [
    (r"\b[Cc]haracters who have a passive (Wisdom|Intelligence) \(\{@skill (\w+)\}\) score of (\d+) or higher (\w+)",
     lambda m: f"Characters who succeed on {an(SKILL_TRAIT[m.group(2).lower()])} <strong>{SKILL_TRAIT[m.group(2).lower()]} Roll ({m.group(3)})</strong> {m.group(4)}"),
    (r"\bAC (\d+)[,;] (\d+) hit points", lambda m: f"Difficulty {m.group(1)}, {dh_hp(m.group(2))} HP"),
    (r"\bAC (\d+)\b", r"Difficulty \1"),
    (r",? and immunity to [a-z, ]+? damage", ""),
    (r"\b(?:is|are) reduced to 0 hit points", "marks its last Hit Point"),
    (r"\bdrops to 0 hit points", "marks its last Hit Point"),
    (r"\breduced to 0 hit points", "with its last Hit Point marked"),
    (r"\bability check, attack roll, or saving throw", "action roll or Reaction Roll"),
    (r"\bsaving throws\b", "Reaction Rolls"), (r"\bsaving throw\b", "Reaction Roll"),
    (r"Melee Weapon Attack: \{@hit (\d+)\} to hit, reach 5 ft\., one target\. Hit: ", r"<em>Melee attack</em> +\1. <em>Hit:</em> "),
    (r"\b([Tt]he|a|that|[Tt]his|each|any) (group )?check\b", r"\1 \2roll"), (r"\bcheck (result|total)", r"roll \1"),
    (r"\b(succeeds|fails) (on )?(the|its|their) (check|save|saving throw)", r"\1 \2\3 roll"),
    (r"\b([Oo]n a) (failed|successful) (save|check)\b", r"\1 \2 roll"), (r"\b(fails|succeeds on) the save\b", r"\1 the roll"),
    (r"\bmakes? a (successful )?save\b", r"makes a \1roll"),
]


def convert_mechanics(s):
    """Rewrite 5e mechanics inside a raw 5etools string (tags still present)."""
    def check(m):
        art, dc, abil, skills, group = m.groups()
        sk = re.findall(r"\{@skill ([^}|]+)", skills or "")
        trait = trait_for(abil, sk, s)
        roll = f"{trait} {'Group Action Roll' if group else 'Roll'} ({dc})"
        return (f"{an(trait)} " if art else "") + f"<strong>{roll}</strong>"

    def save(m):
        art, dc, abil = m.groups()
        trait = ABILITY_TRAIT[abil.lower()]
        return (f"{an(trait)} " if art else "") + f"<strong>{trait} Reaction Roll ({dc})</strong>"

    s = RX_CHECK.sub(check, s)
    s = RX_PLAIN_CHECK.sub(lambda m: trait_for(m.group(1), re.findall(r"\{@skill ([^}|]+)", m.group(2) or ""), s)
                           + (" Rolls" if m.group(3) else " Roll"), s)
    s = RX_SAVE.sub(save, s)
    s = RX_SAVE_DC.sub(lambda m: f"(<strong>Reaction Roll {m.group(1)}</strong>)", s)
    s = RX_DMG.sub(lambda m: f"{{@dice {m.group(1)}}} {'physical' if m.group(2).lower() in PHYSICAL else 'magic'} damage", s)
    s = RX_WITHIN.sub(lambda m: f"within {range_name(m.group(1))} range", s)
    for a, b in GENERIC:
        s = re.sub(a, b, s)
    return s


# ---------- helpers ----------

def rid():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


def slugify_heading(text):
    """Foundry JournalEntryPage.slugifyHeading (String#slugify non-strict, quotes removed, 64 chars)."""
    s = unicodedata.normalize("NFD", text)
    s = "".join(c for c in s if not unicodedata.combining(c)).strip().lower()
    s = re.sub(r"\s+", "-", s)
    return re.sub(r"[\"']", "", s)[:64]


AREA_RX = re.compile(r"^[A-Z]{1,2}\d+[a-z]?\. ")   # keyed map areas: "D4. Burned-out Balloon Factory"
DICE_RX = re.compile(r"^(\d*)d(\d+)$")


def plain(s):
    return re.sub(r"<[^>]+>", "", s)


def words(e):
    return len(re.findall(r"\w+", re.sub(r"\{@\w+ ([^|}]*)[^}]*\}", r"\1", json.dumps(e))))


class Converter:
    def __init__(self, cfg, chapter, idx):
        self.cfg = cfg
        self.chapter = chapter
        self.by_name = {}
        prio = cfg.get("pack_priority", [])
        for e in sorted(idx, key=lambda e: prio.index(e["pack"]) if e["pack"] in prio else len(prio)):
            self.by_name.setdefault((e["doc"], e["name"].lower()), e)
        self.images = {}            # url -> foundry path
        self.anchors = {}           # 5etools id -> (page_id, slug)
        self.mentions = defaultdict(lambda: defaultdict(int))  # creature -> page_id -> count
        self.unmatched = defaultdict(set)
        self.leftovers = defaultdict(list)
        self.page_id = None
        self.journal_id = cfg["journal"]["id"]
        self.area_pages = []        # (page_id, title, html) split out of the current page
        self.in_area = False
        self.tables = []            # RollTable create data
        self.ids = cfg.setdefault("page_ids", {})

    # ----- links -----
    def doc_link(self, doc, name, display, aliases):
        key = name.lower()
        target = aliases.get(key, name) if key in aliases else name
        if target is None:
            self.unmatched[doc].add(name + " (alias: none yet)")
            return f"<em>{str(display)}</em>"
        e = self.by_name.get((doc, target.lower()))
        if not e:
            self.unmatched[doc].add(name)
            return f"<em>{str(display)}</em>"
        return f"@UUID[{e['uuid']}]{{{display}}}"

    def tag(self, m):
        tag, body = m.group(1), m.group(2)
        parts = body.split("|")
        text = parts[0]
        if tag == "creature":
            disp = parts[2] if len(parts) > 2 and parts[2] else text
            self.mentions[text.lower()][self.page_id] += 1
            return self.doc_link("Actor", text, disp, self.cfg.get("aliases", {}))
        if tag == "item":
            disp = parts[2] if len(parts) > 2 and parts[2] else text
            return self.doc_link("Item", text, disp, self.cfg.get("item_aliases", {}))
        if tag in ("spell", "i", "italic", "book", "recipe"):
            return f"<em>{str(parts[-1] if tag == 'book' and len(parts) > 3 else text)}</em>"
        if tag in ("b", "bold"):
            return f"<strong>{str(text)}</strong>"
        if tag == "dice" or tag == "damage":
            return f"[[/r {text}]]"
        if tag == "dc":
            return f"<strong>Difficulty {text}</strong>"
        if tag == "hit":
            return f"+{text}"
        if tag == "condition":
            dh = CONDITIONS.get(text.lower())
            return f"{text} (<strong>{dh}</strong>)" if dh and dh.lower() != text.lower() else (f"<strong>{dh}</strong>" if dh else text)
        if tag == "area":
            ref = parts[1] if len(parts) > 1 else None
            return f"@@AREA[{ref}]{{{text}}}"   # resolved after all pages exist
        if tag == "quickref":
            return str(parts[-1] if len(parts) >= 5 else text)
        if tag == "adventure":
            return f"<em>{str(text)}</em>"
        return str(parts[-1] if len(parts) > 2 and tag in ("filter",) else text)

    def inline(self, s):
        s = convert_mechanics(html.escape(s, quote=False)).replace("\n", "<br>")   # verse lines from PDFs
        # innermost tags first (tags can nest)
        rx = re.compile(r"\{@(\w+) ([^{}]*)\}")
        while rx.search(s):
            s = rx.sub(self.tag, s)
        if LEFTOVER.search(plain(s)):
            self.leftovers[self.page_id].append(plain(s))
        return s

    # ----- entries -----
    def image(self, e):
        path = e.get("href", {}).get("path")
        if e.get("id"): self.anchors.setdefault(e["id"], (self.page_id, None))
        if not path: return ""
        url = self.cfg["img_base"].rstrip("/") + "/" + path
        dest = self.cfg["img_dest"].rstrip("/") + "/" + path.split("/")[-1]
        self.images[url] = dest
        cap = self.inline(e.get("title", "")) if e.get("title") else ""
        return f'<figure><img src="{dest}"><figcaption>{cap}</figcaption></figure>' if cap else f'<p><img src="{dest}"></p>'

    def render(self, e, level):
        if isinstance(e, str):
            return f"<p>{self.inline(e)}</p>"
        if not isinstance(e, dict):
            return ""
        t = e.get("type", "entries")
        out = []
        if e.get("_anchor_id"):
            self.anchors[e["_anchor_id"]] = (self.page_id, None)
        if e.get("id") and e.get("name"):
            self.anchors[e["id"]] = (self.page_id, slugify_heading(plain(self.inline_noreport(e["name"]))))
        elif e.get("id"):
            self.anchors.setdefault(e["id"], (self.page_id, None))
        name = plain(self.inline_noreport(e.get("name", "")))
        if (self.cfg.get("split_areas") and not self.in_area and t in ("entries", "section")
                and AREA_RX.match(name)):
            pid = self.ids.setdefault(f"area:{e.get('id') or name}", rid())
            saved, self.page_id, self.in_area = self.page_id, pid, True
            if e.get("id"): self.anchors[e["id"]] = (pid, None)
            body = "".join(self.render(x, 2) for x in e.get("entries", []))
            self.page_id, self.in_area = saved, False
            self.area_pages.append((pid, name, body))
            return f"<p>📍 @@PAGE[{pid}]{{{name}}}</p>"
        if t in ("entries", "section", "inset", "insetReadaloud", "quote", "variant", "variantInner", "variantSub"):
            body = "".join(self.render(x, level + 1 if e.get("name") else level) for x in e.get("entries", []))
            head = f"<h{min(level, 6)}>{self.inline(e['name'])}</h{min(level, 6)}>" if e.get("name") else ""
            if t == "insetReadaloud":
                return f"<blockquote>{head}{body}</blockquote>"
            if t == "inset":
                return f'<aside class="inset" style="border:1px solid #8884;padding:0.3em 0.8em;margin:0.5em 0">{head}{body}</aside>'
            if t == "quote":
                by = f"<p>— {self.inline(e['by'])}</p>" if e.get("by") else ""
                return f"<blockquote>{body}{by}</blockquote>"
            return head + body
        if t == "list":
            lis = []
            for it in e.get("items", []):
                if isinstance(it, dict) and it.get("type") in ("item", "itemSub"):
                    inner = it.get("entry") or " ".join(x if isinstance(x, str) else "" for x in it.get("entries", []))
                    lis.append(f"<li><strong>{self.inline(it.get('name', ''))}</strong> {self.inline(inner)}</li>")
                elif isinstance(it, str):
                    lis.append(f"<li>{self.inline(it)}</li>")
                else:
                    lis.append(f"<li>{self.render(it, level)}</li>")
            return "<ul>" + "".join(lis) + "</ul>"
        if t == "table" and self.cfg.get("roll_tables") and e.get("colLabels") and DICE_RX.match(plain(e["colLabels"][0]).strip()):
            return self.roll_table(e, level)
        if t == "table":
            cap = f"<caption>{self.inline(e['caption'])}</caption>" if e.get("caption") else ""
            th = "".join(f"<th>{self.inline(c)}</th>" for c in e.get("colLabels", []))
            rows = []
            for r in e.get("rows", []):
                cells = r.get("row", []) if isinstance(r, dict) else r
                rows.append("<tr>" + "".join(f"<td>{self.cell(c, level)}</td>" for c in cells) + "</tr>")
            return f"<table>{cap}<thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        if t == "image":
            return self.image(e)
        if t == "gallery":
            return "".join(self.image(i) for i in e.get("images", []))
        if t == "statblock":
            name = e.get("name") or e.get("source", "")
            return f"<p>📊 {self.doc_link('Actor', name, name + ' (stat block)', self.cfg.get('aliases', {}))}</p>"
        if t in ("inline", "inlineBlock"):
            return "".join(x if isinstance(x, str) else self.render(x, level) for x in e.get("entries", []))
        if t in ("item", "itemSub"):
            inner = e.get("entry") or "".join(self.render(x, level) for x in e.get("entries", []))
            return f"<p><strong>{self.inline(e.get('name', ''))}</strong> {self.inline(inner) if isinstance(inner, str) else inner}</p>"
        if t == "hr":
            return "<hr>"
        return ""  # square/none/flowchart etc.: layout hints only

    def roll_table(self, e, level):
        n, faces = DICE_RX.match(plain(e["colLabels"][0]).strip()).groups()
        name = plain(self.inline(e.get("caption") or "Table"))
        tid = self.ids.setdefault(f"table:{name}", rid())
        labels = [plain(self.inline(c)) for c in e["colLabels"][1:]]
        results = []
        for r in e.get("rows", []):
            cells = r.get("row", []) if isinstance(r, dict) else r
            first = self.cell(cells[0], level)
            nums = [int(x) for x in re.findall(r"\d+", plain(re.sub(r"@@AREA\[[^\]]*\]\{([^}]*)\}", r"\1", first)))]
            lo, hi = (nums[0], nums[-1]) if nums else (len(results) + 1, len(results) + 1)
            if hi == 0: hi = 100 if faces == "100" else hi     # "00" on a d100
            rest = [self.cell(c, level) for c in cells[1:]]
            desc = rest[0] if len(rest) == 1 else "<br>".join(f"<strong>{l}:</strong> {c}" for l, c in zip(labels, rest))
            if "@@AREA" in first:   # the roll number links to the encounter's section: keep it as a ➜ link
                desc = re.sub(r"\{[^}]*\}", "{➜}", first) + " " + desc
            results.append({"type": "text", "name": "", "description": desc,
                            "range": [lo, hi], "weight": hi - lo + 1})
        self.tables.append({"_id": tid, "name": name, "formula": f"{n or 1}d{faces}", "replacement": True,
                            "displayRoll": True, "results": results})
        return f"<p>@Embed[RollTable.{tid} rollable]</p>"

    def autolink(self, c):
        """Link the first plain-text mention per page of each `autolink` actor name (named NPCs the book never tags)."""
        for name in self.cfg.get("autolink", []):
            e = self.by_name.get(("Actor", name.lower()))
            short = self.cfg.get("autolink_text", {}).get(name, name)
            if not e or e["uuid"] in c: continue
            # first occurrence outside tags and outside @UUID[...]{...} labels
            for m in re.finditer(re.escape(short), c):
                before = c[:m.start()]
                if before.count("<") > before.count(">") or before.count("{") > before.count("}"): continue
                if before.endswith("@UUID[") or re.search(r"\w$", before) or re.match(r"\w", c[m.end():m.end() + 1]): continue
                c = before + f"@UUID[{e['uuid']}]{{{short}}}" + c[m.end():]
                break
        return c

    def inline_noreport(self, s):
        return re.sub(r"\{@\w+ ([^|}]*)[^}]*\}", r"\1", s)

    def cell(self, c, level):
        if isinstance(c, dict):
            if c.get("type") == "cell":
                r = c.get("roll", {})
                return str(r.get("exact")) if "exact" in r else f"{r.get('min')}–{r.get('max')}"
            return self.render(c, level)
        return self.inline(str(c))

    # ----- pages -----
    def plan(self):
        if self.cfg.get("pages"):
            by_id = {}
            def walk(e):
                if isinstance(e, dict):
                    if e.get("id"): by_id[e["id"]] = e
                    [walk(x) for x in e.get("entries", [])]
            walk(self.chapter)
            def pick(i):
                if i == "_intro":   # the chapter's unnamed top-level entries
                    return [{"type": "entries", "entries": [e for e in self.chapter["entries"] if not (isinstance(e, dict) and e.get("name"))]}]
                if i.endswith(":lead"):   # a section's unnamed lead entries, without its named children
                    e = by_id[i[:-5]]
                    return [{"type": "entries", "_anchor_id": e.get("id"), "entries": [k for k in e["entries"] if not (isinstance(k, dict) and k.get("name"))]}]
                return [by_id[i]]
            return [(p["title"], [x for i in p["ids"] for x in pick(i)]) for p in self.cfg["pages"]]
        pages, intro = [], []
        limit = self.cfg.get("split_words", 3000)
        for e in self.chapter["entries"]:
            if not (isinstance(e, dict) and e.get("name")):
                intro.append(e); continue
            kids = [k for k in e.get("entries", []) if isinstance(k, dict) and k.get("name")]
            if words(e) > limit and kids:
                lead = [k for k in e["entries"] if not (isinstance(k, dict) and k.get("name"))]
                for i, k in enumerate(kids):
                    pages.append((k["name"], ([{"type": "entries", "entries": lead}] if i == 0 and lead else []) + [k], e["name"] if i == 0 else None))
            else:
                pages.append((e["name"], [e], None))
        if intro:
            pages.insert(0, ("Introduction", intro, None))
        return [(t, es) for t, es, _ in pages]

    def build(self):
        journal = {"_id": self.journal_id, "name": self.cfg["journal"]["name"], "pages": []}
        for title, entries in self.plan():
            self.page_id = self.ids.setdefault(title, rid())
            self.area_pages = []
            body = []
            for uuid in self.cfg.get("page_links", {}).get(title, []):
                body.append(f"<p>🌲 Daggerheart: @UUID[{uuid}]</p>")
            body += self.cfg.get("page_prepend", {}).get(title, [])   # raw HTML, e.g. links to supplements
            for e in entries:
                if isinstance(e, dict) and e.get("name") == title:   # the page title is the h1
                    if e.get("id"): self.anchors[e["id"]] = (self.page_id, None)
                    body += [self.render(x, 2) for x in e.get("entries", [])]
                else:
                    body.append(self.render(e, 2))
            journal["pages"].append({"_id": self.page_id, "name": title, "type": "text",
                                     "sort": (len(journal["pages"]) + 1) * 100000, "title": {"show": True, "level": 1},
                                     "text": {"format": 1, "content": "".join(body)}})
            for pid, name, html_ in self.area_pages:
                journal["pages"].append({"_id": pid, "name": name, "type": "text",
                                         "sort": (len(journal["pages"]) + 1) * 100000, "title": {"show": True, "level": 1},
                                         "text": {"format": 1, "content": html_}})
        for img in self.cfg.get("image_pages", []):
            url = self.cfg["img_base"].rstrip("/") + "/" + img["path"]
            dest = self.cfg["img_dest"].rstrip("/") + "/" + img["path"].split("/")[-1]
            self.images[url] = dest
            pid = self.ids.setdefault(img["title"], rid())
            journal["pages"].append({"_id": pid, "name": img["title"], "type": "image", "src": dest,
                                     "sort": (len(journal["pages"]) + 1) * 100000, "title": {"show": True, "level": 1},
                                     "image": {"caption": img.get("caption", "")}})
        # resolve area links and overrides
        pack = self.cfg["journal"].get("pack")
        base = (f"Compendium.{pack}." if pack else "") + f"JournalEntry.{self.journal_id}.JournalEntryPage."
        def area(m):
            ref, text = m.group(1), m.group(2)
            if ref in self.anchors and self.anchors[ref][0]:
                pid, slug = self.anchors[ref]
                return f"@UUID[{base}{pid}{'#' + slug if slug else ''}]{{{text}}}"
            self.unmatched["Area (other chapter)"].add(f"{text} [{ref}]")
            return f"<em>{text}</em>"
        def fix(c):
            c = re.sub(r"@@AREA\[([^\]]*)\]\{([^}]*)\}", area, c)
            c = re.sub(r"@@PAGE\[([^\]]*)\]\{([^}]*)\}", lambda m: f"@UUID[{base}{m.group(1)}]{{{m.group(2)}}}", c)
            for a, b in self.cfg.get("overrides", []):
                c = c.replace(a, b)
            return c
        for p in journal["pages"]:
            if p["type"] == "text": p["text"]["content"] = self.autolink(fix(p["text"]["content"]))
        for tb in self.tables:
            for r in tb["results"]: r["description"] = fix(r["description"])
        return journal, base


def main(cfg_path, out_dir):
    cfg_path, out = pathlib.Path(cfg_path), pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(cfg_path.read_text())
    cfg["journal"].setdefault("id", rid())
    adv = json.loads(pathlib.Path(cfg["adventure"]).read_text())
    data = (adv.get("adventureData") or adv.get("data"))
    data = data[0]["data"] if isinstance(data, list) and "data" in data[0] else data
    idx = json.loads(pathlib.Path(cfg["index"]).read_text())
    conv = Converter(cfg, data[cfg["chapter"]], idx)
    journal, base = conv.build()
    if cfg["journal"].get("folder"): journal["folder"] = cfg["journal"]["folder"]
    (out / "journal.json").write_text(json.dumps(journal, ensure_ascii=False))
    (out / "images.json").write_text(json.dumps(conv.images, indent=1))
    (out / "tables.json").write_text(json.dumps(conv.tables, ensure_ascii=False))
    anchors = {k: base + p + (f"#{s}" if s else "") for k, (p, s) in conv.anchors.items() if p}
    best = {c: base + max(pages, key=pages.get) for c, pages in conv.mentions.items()}
    (out / "anchors.json").write_text(json.dumps({"ids": anchors, "creature_pages": best}, indent=1, ensure_ascii=False))
    titles = {p["_id"]: p["name"] for p in journal["pages"]}
    rv = ["# Review", "", "## Unmatched links", ""]
    for d, names in conv.unmatched.items():
        rv.append(f"- **{d}**: " + ", ".join(sorted(names)))
    rv += ["", "## 5e leftovers (fix with `overrides`)", ""]
    for pid, lines in conv.leftovers.items():
        rv.append(f"### {titles.get(pid, pid)}")
        rv += [f"- {l[:400]}" for l in dict.fromkeys(lines)]
    (out / "review.md").write_text("\n".join(rv))
    cfg_path.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))   # persist generated ids
    print(f"{journal['name']}: {len(journal['pages'])} pages, {len(conv.tables)} tables, {len(conv.images)} images, "
          f"{sum(len(v) for v in conv.unmatched.values())} unmatched, {sum(len(v) for v in conv.leftovers.values())} leftover lines")
    for p in journal["pages"]:
        print(f"  {p['name']}: " + (f"{len(plain(p['text']['content']).split())} words" if p['type'] == 'text' else p['src']))


if __name__ == "__main__":
    main(*sys.argv[1:3])
