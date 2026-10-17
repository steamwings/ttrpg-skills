// upload-files.js — push files from the cloud workspace into Foundry's Data folder, through the
// user's browser tab (the cloud container has NO network route to the Foundry server).
//
// STEP 1 (javascript_tool): inject a hidden multi-file input.
//   let inp = document.getElementById("claude-upload");
//   if (!inp) { inp = Object.assign(document.createElement("input"), {type: "file", multiple: true, id: "claude-upload"});
//               inp.style.display = "none"; document.body.appendChild(inp); }
//   "ready";
//
// STEP 2: get the input's ref with the `find` tool ("hidden file input claude-upload"), then call
//   mcp__claude-in-chrome__file_upload {ref, tabId, paths: ["/home/claude/work/<map>/a.webp", ...]}
//   (<= 10 MB per call; split big batches). Never click the input — that opens a native dialog.
//   Paths must be under the WORKING DIRECTORY (e.g. /home/claude/work/...). /mnt/user-data/outputs
//   is rejected ("only files this session is allowed to read").
//
// STEP 3 (javascript_tool): run THIS file. ROUTES maps a filename regex to a Data-relative folder.
// What did NOT work: base64 chunks through javascript_tool (180 s timeouts, lost buffers).

const ROUTES = [
  [/^bavlornas-cottage-.*\.webp$/, "assets/maps/prismeer/hither"],
  [/^motherhorn-(stage|tower|understage).*\.webp$/, "assets/maps/prismeer/yon"],
  [/^palace-.*\.webp$/, "assets/maps/prismeer/palace"],
  [/^loomlurch.*\.webp$/, "assets/maps/prismeer/thither"],
  [/.*/, "assets/inbox"],                       // fallback — sort later
];

let out;
try {
  const FP = foundry.applications?.apps?.FilePicker?.implementation ?? FilePicker;
  const inp = document.getElementById("claude-upload");
  if (!inp?.files?.length) throw new Error("no files attached to #claude-upload (run steps 1–2)");
  const ensure = async (path) => {                // create each segment; ignore "already exists"
    let acc = "";
    for (const seg of path.split("/")) {
      acc = acc ? `${acc}/${seg}` : seg;
      try { await FP.createDirectory("data", acc, {}); } catch (e) { /* exists */ }
    }
  };
  const done = [];
  for (const file of inp.files) {
    const dir = ROUTES.find(([re]) => re.test(file.name))[1];
    await ensure(dir);
    const r = await FP.upload("data", dir, file, {}, { notify: false });
    done.push(`${dir}/${file.name}: ${r?.status ?? "?"}`);
  }
  inp.value = "";
  out = done.join("\n");
} catch (e) {
  out = "ERROR: " + e.message;
}
out;
// Verify: (await FP.browse("data", "assets/maps/prismeer/hither")).files
// Foundry has no delete-file API from the client — stray uploads must be removed by the user
// (Setup/host filesystem).
