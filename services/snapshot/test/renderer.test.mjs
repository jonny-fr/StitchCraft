import assert from "node:assert/strict";
import { test } from "node:test";
import { Renderer, RenderError } from "../src/renderer.mjs";

test("concurrency is limited to the configured number", async () => {
  const r = new Renderer({ webUrl: "http://x", concurrency: 2 });
  let active = 0;
  let peak = 0;
  r.renderOnce = async () => {
    peak = Math.max(peak, ++active);
    await new Promise((res) => setTimeout(res, 20));
    active--;
    return Buffer.alloc(1);
  };
  await Promise.all(Array.from({ length: 6 }, () => r.render({})));
  assert.equal(peak, 2);
});

test("a failing render frees its slot", async () => {
  const r = new Renderer({ webUrl: "http://x", concurrency: 1 });
  r.renderOnce = async () => { throw new RenderError("boom", 502); };
  await assert.rejects(r.render({}), /boom/);
  await assert.rejects(r.render({}), /boom/);
});

test("the browser is launched once, shared, and relaunched after a crash", async () => {
  let launches = 0;
  let connected = true;
  const r = new Renderer({ webUrl: "http://x", launch: async () => (launches++, { isConnected: () => connected, close: async () => undefined }) });
  const [a, b] = await Promise.all([r.browserInstance(), r.browserInstance()]);
  assert.equal(a, b);
  assert.equal(await r.browserInstance(), a);
  assert.equal(launches, 1);
  connected = false;
  connected = (await r.browserInstance(), true);
  assert.equal(launches, 2);
  await r.close();
});

test("a failed launch is retried on the next render", async () => {
  let launches = 0;
  const r = new Renderer({ webUrl: "http://x", launch: async () => { throw new Error(`no chromium ${++launches}`); } });
  await assert.rejects(r.render({ key: "a", view: "front", color: "aabbcc", material: "cotton", width: 100, height: 100 }), (e) => e.status === 502);
  await assert.rejects(r.render({ key: "a", view: "front", color: "aabbcc", material: "cotton", width: 100, height: 100 }), (e) => e.status === 502);
  assert.equal(launches, 2);
});

test("an unreachable web app is a 502, not a hang", async () => {
  if (!process.env.SNAPSHOT_REAL) return;
  const r = new Renderer({ webUrl: "http://127.0.0.1:9", timeoutMs: 10_000 });
  await assert.rejects(r.render({ key: "a", view: "front", color: "efe6d2", material: "cotton", width: 200, height: 200 }), (e) => e.status === 502);
  await r.close();
});

// opt-in: SNAPSHOT_REAL=1 STITCHCRAFT_WEB_URL=http://localhost:5199 SNAPSHOT_KEY=<existing preview id> node --test test/
test("real render against a running web app", async (t) => {
  if (!process.env.SNAPSHOT_REAL || !process.env.SNAPSHOT_KEY) return t.skip("set SNAPSHOT_REAL and SNAPSHOT_KEY");
  const r = new Renderer({ webUrl: process.env.STITCHCRAFT_WEB_URL ?? "http://localhost:8080" });
  try {
    const png = await r.render({ key: process.env.SNAPSHOT_KEY, view: "front", color: "efe6d2", material: "cotton", width: 400, height: 300 });
    assert.equal(png.subarray(0, 4).toString("hex"), "89504e47");
    await assert.rejects(r.render({ key: "doesnotexist1", view: "front", color: "efe6d2", material: "cotton", width: 200, height: 200 }), (e) => e.status === 404);
  } finally {
    await r.close();
  }
});
