# World conventions

## Worlds

- **One world per player group**, and it stays the same across campaigns.
  - Example: one group's world (system: daggerheart) starts with *The Wild Beyond the Witchlight* converted
    to Daggerheart; later campaigns for the same group live in that world too.
  - A **different group** gets a different world, so don't merge worlds. Elements get reused by hand, not
    through shared modules.
- No custom modules for content. Use **world-level compendiums** grouped in Compendium Folders:
  - *Witchlight*: Witchlight Scenes / Adversaries / Environments / NPCs / Items / Journals
    (journals: folder `Book` = one entry per chapter, `Expanded` = third-party supplements; see `foundry-adventure-import`)
  - *Group Core*: Group Adversaries / Journals / Tables (for future campaigns of the same group;
    "Group Tables" may duplicate `daggerheart.rolltables`. That's still undecided.)

## Assets (`worlds/<world>/assets/...`, inside the world folder)

```
assets/maps/prismeer/{hither,thither,yon,palace,carnival,generic}/
assets/tokens/{pcs,adversaries,npcs}/
assets/handouts/
assets/journals/<adventure>/<chapter>/   (book art and maps used by journal pages)
assets/audio/{music,ambience,sfx}/
```
Filenames: lowercase-hyphenated, no spaces/parentheses/apostrophes, `.webp` for images.
Multi-floor maps: `<map>-l1.webp`, `-l2`, … (all the same size, grid phase 0, 100px/square).

## Source material

Old Foundry data and loose images may live in the user's cloud storage (ask them to connect it as a folder). Old `my-content-module` packs: `packs/scenes` port fine, while `packs/creatures`
are dnd5e actors and only serve as a checklist.

## Status tracking

Keep a living inventory and migration plan (a doc or artifact) per world. Update it when
milestones land.
