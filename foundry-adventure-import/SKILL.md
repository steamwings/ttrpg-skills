---
name: foundry-adventure-import
description: Import a published adventure's text into Foundry VTT as world journals (one JournalEntry per chapter, a page per section and per keyed map area, maps as image pages, rollable tables), converting D&D 5e mechanics to Daggerheart and linking creatures/items to actors; then back-link actors to their sections and drop GM-only area pins ("D4") on the scenes. Use when preparing an adventure, or a third-party supplement for one, for play in Foundry.
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
   Play content lives in the **world**, not in compendiums: Notes can only open world journals, players can
   be shown world pages, and links stay inside one copy. `foundry-vtt/scripts/move-packs-to-world.js` copies
   compendium actors/items into `Witchlight/...` folders with the same ids and rewrites `Compendium.world.*`
   links; the compendiums stay as backup. Index with `pack: "world"` for world documents.
3. **Convert** a chapter: `scripts/fivetools_to_foundry.py CONFIG OUT` (example config:
   `examples/adventure-config.example.json`). Outputs `journal.json`, `tables.json`, `images.json`, `anchors.json`,
   `review.md`. Options: `split_areas` (a page per "D4. Name" area), `roll_tables` (dice tables → RollTables,
   embedded with `@Embed[RollTable.<id> rollable]`), `autolink` (first plain-text mention per page of named NPCs
   the book never tags), no `journal.pack` = world uuids.
4. **Review** `review.md`: unmatched creatures/items (add `aliases`, `null` = known, no stat block) and 5e
   leftovers. Fix leftovers with `overrides` (exact find/replace on the rendered HTML) and re-run until the list
   holds only harmless lines (dimensions, flavour).
5. **Serve and import**: `scripts/serve_cors.py OUT_DIR 8765 127.0.0.1` (background), then run
   `scripts/import-journal.js` in the `/game` page. It uploads the images (fetched straight from GitHub by the
   browser), replaces the tables and the journal by id. IDs are written back into the config, so re-runs update
   in place and links, Notes and back-links stay valid. Tip: put the function body in the served dir and run
   `(0, eval)(await (await fetch(".../x.fn.js")).text())()` instead of pasting big scripts into `browser_evaluate`.
6. **Back-link actors**: build `actor-links.json` (actor uuid → journal page uuid#anchor + label) and run
   `scripts/link-actors.js`. Pick the section by hand from the mention ranking (first/most mentions); the
   "Roleplaying X" or keyed-area section beats the first mention.
7. **Area pins**: 5etools map images carry `mapRegions` (area id + polygon in book-map pixels).
   `scripts/align_maps.py BOOK_MAP LEVEL_IMG...` finds each scene image in the book map (SIFT + RANSAC; scene
   images cut from the same art come out as pure translations, scale 1.0). Map each region centroid into the level
   whose crop holds it with the largest margin, clamp to the image, then `scripts/create-area-notes.js`: one
   semi-transparent SVG label per area (Note text has no alpha, so the label is drawn into the icon), Note → the
   area's page, `levels` + `elevation` = that level's floor (otherwise a "-10 ft" badge shows). Pins are GM-only
   because the journal's default ownership is NONE. Also set `scene.journal` + `journalEntryPage`.
8. **Look at it**: open a long page, check the TOC, read-aloud boxes, tables, links (`a.content-link.broken`).

## Journal layout

- One JournalEntry per chapter in the world folder `<Adventure>/Book`; supplements in `<Adventure>/Expanded`. Pages: one per top-level section, big locations split out (explicit `pages` plan in the config —
  the automatic `split_words` rule makes tiny pages). Page title = h1, sections h2…, keyed areas keep their
  "D4. Name" headings so they show in the TOC and can be linked.
- Maps: GM and player versions as **image pages** (`image_pages`). A single page can be shown to players
  (right-click it in the journal's page list → Show Players), so handouts don't need their own journals.
- Each location page starts with a link to its Daggerheart **Environment** actor (`page_links`).
- Read-aloud = `<blockquote>`, sidebars = `<aside class="inset">` (ProseMirror keeps both), dice = `[[/r XdY]]`.
- Anchors: Foundry slugs headings with `String#slugify()` non-strict, quotes removed, 64 chars
  (`"D4. Burned-out Balloon Factory"` → `d4.-burned-out-balloon-factory`, `?` stays). `slugify_heading()` matches it.
- World compendium ownership defaults to PLAYER: OBSERVER — players can read anything left in a pack.
- Notes cannot target a heading anchor (only entry + page), which is why keyed areas get their own pages.

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

## Supplement PDFs (DMsGuild, Homebrewery/GMBinder "PHB" style)

`scripts/pdf_to_fivetools.py PDF OUT.json --skip <cover,credits,ads> --title ... --known creatures.json
[--move "Child>Parent"]` rebuilds the structure from font roles (see its docstring) as a 5etools-like chapter, so the
same converter, rules, area pages and links apply (`adventure` = OUT.json, `chapter` = 0). It re-tags DCs, skills,
dice and conditions, turns bold creature names from `--known` into `{@creature}`, keeps verse line breaks (`\n` →
`<br>`), merges drop caps and de-duplicates shadowed headings. `--move` fixes sidebars that land in the wrong section
(reading order follows the content stream). It also writes `OUT.statblocks.json`: the raw 5e stat blocks to convert.
`pymupdf`: `pip install pymupdf --break-system-packages`; run with `python3 -P -E`, not `-I` (that drops user
site-packages). Supplement journals go to `<Adventure>/Expanded`; link them from the book chapter with `page_prepend`.

## Converting creatures (Daggerheart, not 5e with new numbers)

- Match the region's tier and the world's existing adversaries (Hither = Tier 2: Difficulty 13–16, HP 3–8, Stress
  2–5, thresholds ~7/14 for small fry to ~13/26 for solos, attacks +1..+4 with 2dX+N damage).
- Pick the adversary **type** by its job in the scene (standard, skulk, bruiser, leader, solo, social, minion…).
- Features are text in the world's style: `@Lookup[@name]`, **Spend a Fear** for big moves, **Mark a Stress** for
  repeatables, Reaction Rolls with a trait and Difficulty, DH conditions (Vulnerable, Restrained, Hidden), ranges.
  Turn 5e bookkeeping (auras on turn start, recharge, legendary actions) into spotlight-driven moves.
- Put the scene's tricks (terrain, puzzles, social stakes) on an **Environment** actor with potential adversaries.
- Friendly NPCs are `npc` actors: short description, motives, notes with roleplay hooks and "in a fight, use X".
- Data lives in a per-supplement generator script with fixed ids (ids.json) → `scripts/create-docs.js`
  (delete + recreate by id, so re-run `link-actors.js` afterwards).

## Keep copyrighted text out of this repo

Configs with overrides, extracted text and outputs hold book text: keep them in a work directory, never here.
