---
name: foundry-adventure-import
description: Import a published adventure's text into Foundry VTT as compendium journals (one JournalEntry per chapter, a page per section, maps as image pages), converting D&D 5e mechanics to Daggerheart and linking creatures/items to existing actors; then back-link actor descriptions to their journal sections. Use when preparing an adventure, or a third-party supplement for one, for play in Foundry.
---

# Adventure import (5etools JSON / supplement PDFs → Foundry journals)

The text the GM needs at the table goes into **GM-only journals**. Actors stay short: the sheet shows the features,
and one "📖" line links to the journal section with the long version (personality, secrets, where they appear).

## Pipeline

1. **Source**: the 5etools adventure JSON (`data/adventure/adventure-<id>.json` in the 5etools source repo on
   GitHub; the website itself sits behind a Cloudflare human check, so don't drive it). Images live in the
   matching `5etools-img` repo. Third-party supplements come as PDFs: extract with PyMuPDF (see below).
2. **Index the world**: dump every Actor/Item compendium index from the Foundry tab to `foundry-index.json`
   (`[{pack, doc, name, type, uuid, folder}]`) so the converter can link names.
3. **Convert** a chapter: `scripts/fivetools_to_foundry.py CONFIG OUT` (example config:
   `examples/adventure-config.example.json`). Outputs `journal.json`, `images.json`, `anchors.json`, `review.md`.
4. **Review** `review.md`: unmatched creatures/items (add `aliases`, `null` = known, no stat block) and 5e
   leftovers. Fix leftovers with `overrides` (exact find/replace on the rendered HTML) and re-run until the list
   holds only harmless lines (dimensions, flavour).
5. **Serve and import**: `scripts/serve_cors.py OUT_DIR 8765` (background), then run `scripts/import-journal.js`
   in the `/game` page. It uploads the images (fetched straight from GitHub by the browser) and replaces the
   journal by id. IDs are written back into the config, so re-runs update in place and links stay valid.
6. **Back-link actors**: build `actor-links.json` (actor uuid → journal page uuid#anchor + label) and run
   `scripts/link-actors.js`. Pick the section by hand from the mention ranking (first/most mentions); the
   "Roleplaying X" or keyed-area section beats the first mention.
7. **Look at it**: open a long page, check the TOC, read-aloud boxes, tables, links (`a.content-link.broken`).

## Journal layout

- One JournalEntry per chapter in the adventure's journal compendium, compendium folder `Book`; supplements in
  `Expanded`. Pages: one per top-level section, big locations split out (explicit `pages` plan in the config —
  the automatic `split_words` rule makes tiny pages). Page title = h1, sections h2…, keyed areas keep their
  "D4. Name" headings so they show in the TOC and can be linked.
- Maps: GM and player versions as **image pages** (`image_pages`). A single page can be shown to players
  (right-click it in the journal's page list → Show Players), so handouts don't need their own journals.
- Each location page starts with a link to its Daggerheart **Environment** actor (`page_links`).
- Read-aloud = `<blockquote>`, sidebars = `<aside class="inset">` (ProseMirror keeps both), dice = `[[/r XdY]]`.
- Anchors: Foundry slugs headings with `String#slugify()` non-strict, quotes removed, 64 chars
  (`"D4. Burned-out Balloon Factory"` → `d4.-burned-out-balloon-factory`, `?` stays). `slugify_heading()` matches it.
- Compendium ownership defaults to PLAYER: OBSERVER — players could read the whole adventure. Set the
  journal pack to NONE for players.

## 5e → Daggerheart rules (in the converter)

| 5e | Daggerheart |
|---|---|
| DC N Ability (Skill) check | **Trait Roll (N)**; group check → **Trait Group Action Roll (N)** |
| DC N Ability saving throw / (save DC N) | **Trait Reaction Roll (N)** |
| Skills | Athletics→Strength, Acrobatics→Agility, Sleight of Hand/Stealth→Finesse, Arcana/History/Investigation/Nature/Religion/Medicine→Knowledge, Animal Handling/Insight/Perception/Survival→Instinct, Deception/Intimidation/Performance/Persuasion→Presence |
| Abilities | Str/Con→Strength, Dex→Agility (Finesse for locks/thieves' tools), Int→Knowledge, Wis→Instinct, Cha→Presence |
| passive Perception N | Instinct Roll (N) |
| X (NdM) type damage | NdM physical (bludgeoning/piercing/slashing) or magic damage |
| within N feet | Melee ≤5, Very Close ≤10, Close ≤30, Far ≤100, Very Far beyond |
| AC N, M hit points (objects) | Difficulty N, round(M/6) HP (min 1); immunities dropped |
| reduced to / drops to 0 hp | marks its last Hit Point |
| prone, stunned, paralyzed, blinded / restrained, grappled / invisible | Vulnerable / Restrained / Hidden |

Speeds, darkvision, temporary hit points and hit point arithmetic need a human sentence: use `overrides`.
Spells stay as italic flavour (no Daggerheart equivalents).

## Supplement PDFs

`pymupdf` (`pip install pymupdf --break-system-packages`; run scripts with `python3 -P -E`, not `-I`, or the
user site-packages vanish). Plain `get_text()` duplicates running headers and splits drop caps ("M\nystery").

## Keep copyrighted text out of this repo

Configs with overrides, extracted text and outputs hold book text: keep them in a work directory, never here.
