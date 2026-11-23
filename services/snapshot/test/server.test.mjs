import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";
import { RenderError } from "../src/renderer.mjs";
import { createApp } from "../src/server.mjs";
import { InputError, parseRequest, snapshotQuery } from "../src/validate.mjs";

const PNG = Buffer.from("89504e470d0a1a0a", "hex");

describe("parseRequest", () => {
  test("fills defaults and lower-cases the colour", () => {
    assert.deepEqual(parseRequest({ key: "abc123", color: "A1B2C3" }), {
      key: "abc123", view: "front", color: "a1b2c3", material: "cotton", width: 800, height: 600,
    });
  });
  const bad = [
    [null, /JSON object/], [[], /JSON object/], [{}, /key/], [{ key: "../x" }, /key/], [{ key: "a".repeat(65) }, /key/],
    [{ key: "a", view: "bottom" }, /view/], [{ key: "a", color: "#aabbcc" }, /color/], [{ key: "a", color: "red" }, /color/],
    [{ key: "a", material: "silk" }, /material/], [{ key: "a", width: 10 }, /width/], [{ key: "a", height: 99999 }, /height/],
    [{ key: "a", width: "800" }, /width/], [{ key: "a", height: 1.5 }, /height/],
  ];
  for (const [body, re] of bad) test(`rejects ${JSON.stringify(body)}`, () => assert.throws(() => parseRequest(body), (e) => e instanceof InputError && re.test(e.message)));
  test("query carries all fields", () => {
    assert.equal(snapshotQuery({ key: "k", view: "iso", color: "aabbcc", material: "mohair" }), "snapshot=k&view=iso&color=aabbcc&material=mohair");
  });
});

describe("HTTP", () => {
  let server, base, behaviour;
  before(async () => {
    server = createApp({ render: async (o) => behaviour(o) });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    base = `http://127.0.0.1:${server.address().port}`;
  });
  after(() => server.close());
  const post = (body, raw) => fetch(`${base}/render`, { method: "POST", body: raw ?? JSON.stringify(body) });

  test("health", async () => {
    const r = await fetch(`${base}/health`);
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), { status: "ok" });
  });
  test("render returns the PNG and passes the options on", async () => {
    let seen;
    behaviour = (o) => ((seen = o), PNG);
    const r = await post({ key: "abc", view: "top" });
    assert.equal(r.status, 200);
    assert.equal(r.headers.get("content-type"), "image/png");
    assert.deepEqual(Buffer.from(await r.arrayBuffer()), PNG);
    assert.equal(seen.view, "top");
  });
  test("invalid input is 400 and never reaches the renderer", async () => {
    behaviour = () => assert.fail("rendered");
    for (const r of [await post({ key: "../etc" }), await post(null, "not json"), await post({ key: "a" }, "x".repeat(5000))]) {
      assert.equal(r.status, 400);
      assert.ok((await r.json()).error);
    }
  });
  test("renderer errors keep their status", async () => {
    behaviour = () => { throw new RenderError("unknown preview abc", 404); };
    assert.equal((await post({ key: "abc" })).status, 404);
    behaviour = () => { throw new RenderError("render timed out", 504); };
    assert.equal((await post({ key: "abc" })).status, 504);
  });
  test("unexpected errors are 500 without details", async () => {
    behaviour = () => { throw new Error("secret path /x"); };
    const origError = console.error;
    console.error = () => undefined;
    try {
      const r = await post({ key: "abc" });
      assert.equal(r.status, 500);
      assert.equal((await r.json()).error, "internal error");
    } finally {
      console.error = origError;
    }
  });
  test("unknown path 404, wrong method 405", async () => {
    assert.equal((await fetch(`${base}/nope`)).status, 404);
    assert.equal((await fetch(`${base}/render`)).status, 405);
  });
});
