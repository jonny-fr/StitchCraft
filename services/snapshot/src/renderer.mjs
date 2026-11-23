import { chromium } from "playwright";
import { snapshotQuery } from "./validate.mjs";

// same flags as web/playwright.config.ts: WebGL on the CPU, no GPU in the container
const ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];

export class RenderError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** One shared Chromium; every render gets its own context, at most `concurrency` at a time. */
export class Renderer {
  constructor({ webUrl, timeoutMs = 60_000, concurrency = 1, launch = (o) => chromium.launch(o) }) {
    this.launch = launch;
    this.webUrl = webUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
    this.free = concurrency;
    this.waiting = [];
    this.browser = null;
    this.launching = null;
  }

  /** The running browser, relaunched when it crashed or was never started. */
  async browserInstance() {
    if (this.browser?.isConnected()) return this.browser;
    this.launching ??= this.launch({ args: ARGS }).finally(() => (this.launching = null));
    this.browser = await this.launching;
    return this.browser;
  }

  async acquire() {
    if (this.free > 0) return void this.free--;
    await new Promise((resolve) => this.waiting.push(resolve));
  }

  release() {
    const next = this.waiting.shift();
    if (next) next();
    else this.free++;
  }

  async render(options) {
    await this.acquire();
    try {
      return await this.renderOnce(options);
    } finally {
      this.release();
    }
  }

  async renderOnce(options) {
    let context;
    try {
      const browser = await this.browserInstance();
      context = await browser.newContext({ viewport: { width: options.width, height: options.height }, deviceScaleFactor: 1, colorScheme: "light" });
      const page = await context.newPage();
      page.setDefaultTimeout(this.timeoutMs);
      await page.goto(`${this.webUrl}/?${snapshotQuery(options)}`);
      await page.waitForFunction(() => window.__stitchcraftSnapshot === "ready" || window.__stitchcraftSnapshot === "error", null, { timeout: this.timeoutMs });
      if ((await page.evaluate(() => window.__stitchcraftSnapshot)) === "error") throw new RenderError(`unknown preview ${options.key}`, 404);
      return await page.screenshot({ type: "png" });
    } catch (err) {
      if (err instanceof RenderError) throw err;
      if (err?.name === "TimeoutError") throw new RenderError(`render timed out after ${this.timeoutMs} ms`, 504);
      throw new RenderError(`render failed: ${String(err?.message ?? err).split("\n")[0]}`, 502);
    } finally {
      await context?.close().catch(() => undefined);
    }
  }

  async close() {
    await this.launching?.catch(() => undefined);
    await this.browser?.close().catch(() => undefined);
  }
}
