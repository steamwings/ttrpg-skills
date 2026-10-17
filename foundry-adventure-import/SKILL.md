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
   the book never tags; never inside headings, which become anchors), no `journal.pack` = world uuids.
4. **Review** `review.md`: unmatched creatures/items (add `aliases`, `null` = known, no stat block) and 5e
   leftovers. Fix leftovers with `overrides` (exact find/replace on the rendered HTML) and re-run until the list
   holds only harmless lines (dimensions, flavour).
5. **Serve and import**. Best: let Playwright answer `http://localhost:8765/*` from a local folder, no server process
   (background commands get killed after 2 h):
   `browser_run_code_unsafe`: `page.context().route("http://localhost:8765/**", r => r.fulfill({path: ROOT + name,
   headers: {"Access-Control-Allow-Origin": "*"}}))` (register once per browser context; re-navigate to /game after).
   Fallback: `scripts/serve_cors.py OUT_DIR 8765 127.0.0.1` in the background. Every browser script reads
   `globalThis.__IMPORT_BASE ?? "http://localhost:8765"` plus optional `import.json` options, so one served tree can hold
   several jobs in sub-folders (`__IMPORT_BASE = ".../scene-cove"`). Then run
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
8. **Tokens**: list who the text puts in each area (`[{area, actor, count, linked}]`), `scripts/plan_tokens.py PINS SPEC
   OUT --grid N` spreads them over grid cells inside the area polygon (nearest the centroid, never under the pin),
   `scripts/place-tokens.js` creates them **hidden**, at the level's elevation, importing SRD actors into the world
   first. Unique NPCs linked, generic adversaries unlinked. Creatures that move on a schedule (the hags) go where
   the text first meets them; say so in the token spec `note`.
9. **Look at it**: open a long page, check the TOC, read-aloud boxes, tables, links (`a.content-link.broken`).

## Supplement maps → play-ready scenes

Supplement maps have no `mapRegions`, and painterly maps often defeat auto-walls. Trace each keyed room once on a
downscaled crop and write a spec (`scripts/scene_from_spec.py` docstring): rooms (polygon + doors + secret doors →
walls, an Interior darkness region, lights), open areas (pins only), tokens. Rooms that share a wall each draw it;
`clear_doorways` cuts every wall where a door overlaps it and drops duplicates. Then `scripts/build-scene.js`
(uploads the map, grid from the file name, e.g. `grid-32x21-160ppi` → 160 px squares; day/night rule; replaces only
its own walls/lights/region), `create-area-notes.js`, `plan_tokens.py` + `place-tokens.js`. Outdoor maps (terraces,
floating isles) get no edge walls: jumping and climbing are narrated with the environment's rules.

**Connected maps are one scene with Levels.** Before building a scene, check how the text connects it to others
(stairs, a trapdoor, "beneath", "descends"). A den under a building, a cellar, the floors of a tower: one scene, one
V14 Level per map (elevation bands, e.g. den −10..0 under a 0..20 ground floor) and a `changeLevel` region on the
stairs, on both levels. Paste the smaller map onto a canvas the size of the main level image, offset so the staircases
line up (snap the offset to the grid). `scripts/merge-scene-as-level.js` folds an already-built scene into another.
Side-by-side composites of floors are only a fallback.

Light animation types (V14) include flame, torch, pulse, wave, fairy, starlight (there is no "fire"); `"anim": null`
gives a steady light. Several floors drawn as separate images can be composited side by side (PIL) into one scene.
Run `scripts/check-icons.js` on every generator's icon list before creating documents.

## Official art and backdrops

- **Actor art**: important NPCs get the book's art instead of a generic icon. Bestiary fluff images
  (`bestiary/<SRC>/<Name>.webp`) and book illustrations (`adventure/<SRC>/...`, list them from the adventure JSON's
  `image` entries) go in `MAP.json`; give a crop (`[cx, cy, size]`) to any actor whose token is generic or missing,
  then `scripts/book_art.py MAP CROPS WORK` (portraits + round 400 px tokens, `tokens-preview.jpg` to check the
  faces) and `scripts/apply-art.js` (sets `img`, prototype token and placed tokens). Group shots make poor tokens:
  keep the old token or crop one figure. Generators should set the same `img`/`token` (`create-docs.js` reads
  `token`), or a re-run puts the old art back.
- **Backdrops** (mood art, no tokens): `scripts/create-backdrops.js` makes "theater" scenes (no grid, vision or fog)
  in `Backdrops/<region>`: players see the place name, the GM sees "BG · name". Each links its journal page and gets
  a GM pin to it, and the page gets a 🎬 line linking the backdrop and, when there is one, the battle map that comes
  next. Use them for travel, arrivals and talk, then switch to the map when the fight or exploration starts. Re-run it
  after re-importing a journal (the 🎬 lines live in the page).
- **Illustrated maps without regions** (a carnival poster, a region map): place the pins by hand in percent of the
  image, one pin per location page, with 2–3 letter labels; NPC tokens hidden next to where the text puts them.

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

Speeds, darkvision, temporary hit points and hit point arithmetic need a human sentence: use `overrides` (exact),
`overrides_re` (regex, DOTALL, for whole blocks), `page_replace` (a hand-written Daggerheart page, e.g. magic items),
and `extra_tables` + `@@TABLE[name]` (a 5e table rewritten as a Daggerheart RollTable).
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

- **Keep it lean: 3–5 features** (the GM found 8 on one sheet too many). Fold movement quirks, immunities and flavour
  into the description or into one combined passive; keep one signature Fear move, one or two actions, and the
  scene-defining reaction (surrender, death trigger). Socials/solos may go to 5.
- Match the region's tier and the world's existing adversaries (Hither = Tier 2: Difficulty 13–16, HP 3–8, Stress
  2–5, thresholds ~7/14 for small fry to ~13/26 for solos, attacks +1..+4 with 2dX+N damage).
- Pick the adversary **type** by its job in the scene (standard, skulk, bruiser, leader, solo, social, minion…).
- Features are text in the world's style: `@Lookup[@name]`, **Spend a Fear** for big moves, **Mark a Stress** for
  repeatables, Reaction Rolls with a trait and Difficulty, DH conditions (Vulnerable, Restrained, Hidden), ranges.
  Turn 5e bookkeeping (auras on turn start, recharge, legendary actions) into spotlight-driven moves.
- Put the scene's tricks (terrain, puzzles, social stakes) on an **Environment** actor with potential adversaries.
- Friendly NPCs are `npc` actors: short description, motives, notes with roleplay hooks and "in a fight, use X".
- Data lives in a per-supplement generator script with fixed ids (ids.json) → `scripts/create-docs.js`
  (delete + recreate by id, so re-run `link-actors.js` afterwards). Damage types are `physical` / `magical`.
  Check every `icons/...` path exists (HEAD request) before creating; many guessed core icon names don't.
- Back-links: `scripts/build_links.py JOURNAL PREFIX SPEC OUT` with readable targets (`"Page > Heading"`); it fails
  on targets a re-split journal no longer has.
- Handouts: `scripts/make_handouts.py` → one "Handouts: <region>" journal of image pages per region.

## World ↔ compendium sync

The world is the source of truth during prep and play. At the end of a session run
`foundry-vtt/scripts/sync-world-to-packs.js` (DRY_RUN first): it copies everything under the adventure's root folders
into the world compendiums with the same ids, mirrors folders, rewrites links to compendium uuids, and creates the
tables pack if needed. `move-packs-to-world.js` is the exact inverse. Set those packs to PLAYER: NONE.

## Keep copyrighted text out of this repo

Configs with overrides, extracted text and outputs hold book text: keep them in a work directory, never here.
