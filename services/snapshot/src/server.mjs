import { createServer } from "node:http";
import { Renderer, RenderError } from "./renderer.mjs";
import { InputError, parseRequest } from "./validate.mjs";

const MAX_BODY = 4096;

function send(res, status, body, type = "application/json") {
  res.writeHead(status, { "content-type": type, "content-length": Buffer.byteLength(body) });
  res.end(body);
}
const fail = (res, status, error) => send(res, status, JSON.stringify({ error }));

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    if ((size += chunk.length) > MAX_BODY) throw new InputError("body too large");
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new InputError("body is not valid JSON");
  }
}

export function createApp(renderer) {
  return createServer(async (req, res) => {
    try {
      const path = new URL(req.url ?? "/", "http://x").pathname;
      if (req.method === "GET" && path === "/health") return send(res, 200, JSON.stringify({ status: "ok" }));
      if (path !== "/render") return fail(res, 404, "not found");
      if (req.method !== "POST") return fail(res, 405, "use POST");
      const options = parseRequest(await readJson(req));
      send(res, 200, await renderer.render(options), "image/png");
    } catch (err) {
      if (err instanceof InputError) return fail(res, 400, err.message);
      if (err instanceof RenderError) return fail(res, err.status, err.message);
      console.error(err);
      fail(res, 500, "internal error");
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const renderer = new Renderer({
    webUrl: process.env.STITCHCRAFT_WEB_URL ?? "http://localhost:8080",
    timeoutMs: Number(process.env.STITCHCRAFT_RENDER_TIMEOUT_MS ?? 60_000),
    concurrency: Number(process.env.STITCHCRAFT_SNAPSHOT_CONCURRENCY ?? 1),
  });
  const port = Number(process.env.STITCHCRAFT_SNAPSHOT_PORT ?? 8770);
  const server = createApp(renderer).listen(port, "0.0.0.0", () => console.log(`snapshot service on :${port}`));
  for (const sig of ["SIGTERM", "SIGINT"])
    process.on(sig, () => server.close(() => renderer.close().then(() => process.exit(0))));
}
