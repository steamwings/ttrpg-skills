// upload-via-playwright.js — push one workspace file into Foundry's Data folder with the Playwright MCP,
// no file server and no file chooser. Run with browser_run_code_unsafe (it gets `page`), on a /game tab.
// page.route answers a fake URL with the local file; the page fetches it and calls FilePicker.upload.
// Edit SRC / DIR / NAME. The MCP only reads files under its allowed roots (e.g. ~/.playwright-mcp).
// Foundry has no client-side delete: a wrong upload must be removed by the user.
async (page) => {
  const SRC = "/home/coder/.playwright-mcp/maps/example.webp";
  const DIR = "assets/maps/prismeer/hither", NAME = "example.webp", TYPE = "image/webp";
  await page.route("https://claude-upload.local/**", r =>
    r.fulfill({ path: SRC, headers: { "Access-Control-Allow-Origin": "*", "Content-Type": TYPE } }));
  try {
    return await page.evaluate(async ({ DIR, NAME, TYPE }) => {
      const FP = foundry.applications.apps.FilePicker.implementation;
      const blob = await (await fetch("https://claude-upload.local/" + NAME)).blob();
      const r = await FP.upload("data", DIR, new File([blob], NAME, { type: TYPE }), {}, { notify: false });
      return { size: blob.size, status: r?.status, path: r?.path };
    }, { DIR, NAME, TYPE });
  } finally {
    await page.unroute("https://claude-upload.local/**");
  }
}
