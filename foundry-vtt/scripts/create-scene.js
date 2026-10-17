// create-scene.js — new V14 scene whose Levels use grid-aligned images (see map-prep).
// All level images must be the same size (WIDTH x HEIGHT) with the grid phase at 0.
// Fails if a scene with that name exists (rename or delete it first; never overwrite silently).
const NAME = "Loomlurch";
const WIDTH = 3800, HEIGHT = 5300;           // image px
const GRID = { size: 100, distance: 10, units: "ft" };   // READ THE MAP LEGEND: 5 ft vs 10 ft!
const LEVELS = [                             // bottom -> top; one entry = single-level scene
  { name: "Loomlurch", bottom: 0, top: 20, src: "assets/maps/prismeer/thither/loomlurch.webp" },
];

let out;
try {
  if (game.scenes.getName(NAME)) throw new Error(`scene already exists: ${NAME}`);
  const s = await Scene.create({
    name: NAME, width: WIDTH, height: HEIGHT, padding: 0.05,
    grid: { type: 1, style: "solidLines", thickness: 1, color: "#000000", alpha: 0.2, ...GRID },
    tokenVision: true, fog: { mode: 1 },
    levels: LEVELS.map(l => ({ name: l.name, elevation: { bottom: l.bottom, top: l.top }, background: { src: l.src } })),
  });
  const first = s.levels.contents[0];
  if (first) await s.update({ initialLevel: first.id });
  // Stacked floors normally see only themselves: set visibility.levels per Level if needed.
  out = JSON.stringify({ id: s.id, sceneX: s.dimensions.sceneX, sceneY: s.dimensions.sceneY,
    levels: s.levels.map(l => ({ id: l.id, name: l.name })) });
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
