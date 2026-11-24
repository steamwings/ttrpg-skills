---
name: daggerheart-encounters
description: Design and build a Daggerheart encounter in a Foundry V14 world (Foundryborne system) - Battle Points budget, lean custom adversaries, an Environment actor, countdowns, a battle map, hidden tokens and a GM page. Use when the GM asks for a fight, chase or set piece for the next session.
---

# Daggerheart encounters (design + Foundry build)

Builds on `foundry-vtt` (connection, browser JS rules) and `foundry-adventure-import` (lean creature rules).
Ground every pitch in the world first: read the GM's notes journals, the PCs' sheets (level, Evasion, HP,
thresholds, class features) and the adversaries already built. Keep the GM's labels (e.g. [Seed] vs [Decided]).

## Design

- **Budget (Battle Points):** (3 × PCs) + 2. Costs: minions 1 per group of party size, social/support 1,
  horde/ranged/skulk/standard 2, leader 3, bruiser 4, solo 5. Adjust: −1 short/easy fight, −2 for 2+ solos,
  −2 if every adversary gets +1d4 (or +2) damage, +1 per lower-tier adversary, +1 with no bruiser/horde/leader/solo,
  +2 for a long/hard fight. Write the arithmetic on the GM page.
- **Match the PCs' tier, not the region's.** A level 1 party in a "Tier 2 region" fights Tier 1 builds.
- **Stakes beyond HP.** Put the stakes on a countdown about something the PCs care about (a carried item, a
  person, an escape) and say what happens at 0. Failing forward beats a TPK. Offer 2–3 ways it can end.
- **Spotlight each PC from their sheet** (low Evasion + high Armor = the one who gets grabbed and braces; a bomb
  user gets a target only bombs can reach). Check PC features that cancel your moves (e.g. Guardian's
  Unstoppable: can't be Restrained or Vulnerable) and note them.
- **Higher-tier NPCs met early** (a named villain at Tier 3 vs level 1 PCs): run them as forces in the scene, not
  stat blocks. Pull their punches explicitly (an environment feature: "a hit makes the PC mark a Stress; spend a
  Fear to make it real, at Tier 1 damage") and give them an exit (invisibility, flight). Rolls move countdowns, not HP.
- **Recurring enemies** need a rule for "defeated" (unravel, re-form later at a cost) and a way to end them for
  good. Record it once in the lore journal so later sessions stay consistent.
- **Back-pocket minions:** hidden tokens the GM spends a Fear to bring in when a table needs a taste of combat.
- **Low Fear?** Remind the GM: moves on failures, rolls with Fear and "players look to you" cost nothing; Fear
  buys extra moves. Prefer features that earn Fear (Momentum) or cost Stress over ones that cost Fear.

## Foundry build (one idempotent script, run with `browser_run_code_unsafe`)

Write a per-encounter script that **aborts if any name already exists**, then creates, in order:
lore/page links it needs → adversaries → scene + tokens → environment → GM page → map note → countdowns.

- **Adversaries:** copy an existing world adversary's `system.toObject()` as a template (its `attack` object
  has the right shape). Set `tier`, `type`, `difficulty`, `resources.hitPoints/stress.max`, `damageThresholds`,
  `attack.roll.bonus` (string), `attack.range` (`melee|veryClose|close|far|veryFar`), `attack.damage.main.type`
  (`["physical"]|["magical"]`) and `attack.damage.main.value` (`{multiplier:"flat", flatMultiplier:1, dice:"d8",
  bonus:2}`, or `custom:{enabled:true, formula:"2"}` for minions). Experiences: `{[randomID]: {name, value, description}}`.
- **Features** are `feature` items: `{name, type:"feature", img, system:{description, featureForm:
  "passive|action|reaction", actions:{}, ...}}`. Copy SRD ones (Horde, Minion (3), Group Attack, Split,
  Acidic Form) from `daggerheart.adversaries` with `items.getName(n).toObject()` minus `_id`.
- **Horde:** `typeData: {type:"horde", hordeHP: <creatures per HP>, hordeDamage: "1d4+1"}`. Minions: `typeData: null`.
- **Token size follows `system.size`** (`medium`=1, `large`=2, ...; `custom` = use the token's own width/height).
  Setting a prototype width alone gets overwritten.
- **Environment actor:** `type:"environment"`, `system:{tier, type:"event|exploration|social|traversal",
  difficulty, impulses, potentialAdversaries:{[randomID]:{label, adversaries:["Actor.id", ...]}}}` + 3–5 features.
- **Countdowns** live in the world setting `daggerheart.Countdowns`: `toObject()`, add
  `{type:"encounter", name, img, hidden:true, ownership:{}, progress:{current, start, looping:"noLooping",
  type:"custom"}}`, `game.settings.set(...)`. Remove one by rebuilding `countdowns` without its key (a `-=` key
  does not work here). **Automatic progressions (`fear`, `actionRoll`, ...) tick while hidden**, so prepped
  countdowns should be `custom` (manual) until the scene starts. The GM reveals with right-click → Reveal Countdown.
- **Scene:** the `create-scene.js` shape (single Level). Hidden adversary tokens, PC tokens at the entry,
  a GM Note pinned to the encounter page. For fog that really hides people: global light off
  (`darknessLevel` above `globalLight.darkness.max`), placed PC tokens `sight:{enabled:true, range:30,
  visionMode:"basic"}`, `weather:"fog"`. Lit areas are visible at any range, so lights read as "lights in the fog".
- **No map art?** The `map-generate` skill makes a grid-aligned battle map from a layout spec, plus a scene.json
  of walls and lights. Upload it with `foundry-vtt/scripts/upload-via-playwright.js`, or build the scene with
  `build-scene.js`.
- **GM page** (in the GM's notes journal): links (scene, environment, countdowns, lore), the idea, budget,
  read-aloud per group (`<blockquote>`), countdown rules, NPC handling, back pocket, ways it ends, aftermath.
  Back-link it from the environment and adversary descriptions (📖 line).

## Verify

`scene.view()` (your client only), screenshot, open the new sheets, then `game.scenes.active.view()` to go back.
Never `activate()` a scene or toggle pause in a live world: players may be online (`game.users.filter(u => u.active)`).
