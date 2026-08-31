import { createServer } from "node:http";

const MAX_BODY_BYTES = 32_768;

const sendJson = (response, status, payload) => {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store"
  });
  response.end(body);
};

const readJson = async (request) => {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new Error("PAYLOAD_TOO_LARGE");
    chunks.push(chunk);
  }
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
};

const localUrl = (value) => {
  const parsed = new URL(value);
  if (!["127.0.0.1", "localhost"].includes(parsed.hostname)) throw new Error("NAVIGATION_BLOCKED");
  return parsed.href;
};

export const startBrowserBridge = async ({ page, getPage, token, port = 8765 }) => {
  if (!token || token.length < 24) throw new Error("CUA_APP_SECRET tidak valid untuk browser bridge.");

  const currentPage = () => getPage?.() ?? page;
  const currentBrowserPage = () => currentPage().page?.() ?? currentPage();
  const currentKeyboard = () => currentPage().keyboard ?? currentPage().page?.().keyboard;
  const locate = (payload) => currentPage().getByRole(payload.role, {
    ...(payload.name ? { name: payload.name } : {}),
    exact: payload.exact !== false
  });

  const server = createServer(async (request, response) => {
    try {
      if (request.headers.authorization !== `Bearer ${token}`) {
        sendJson(response, 401, { error: "UNAUTHORIZED" });
        return;
      }
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      if (request.method === "GET" && url.pathname === "/health") {
        const browserVersion = await currentPage().evaluate(() => navigator.userAgent);
        sendJson(response, 200, {
          status: "ready",
          page_url: currentPage().url(),
          browser_version: browserVersion
        });
        return;
      }
      if (request.method === "GET" && url.pathname === "/page/meta") {
        sendJson(response, 200, { url: currentPage().url(), title: await currentPage().title() });
        return;
      }
      if (request.method === "GET" && url.pathname === "/page/screenshot") {
        const viewport = await currentPage().evaluate(() => ({
          width: window.innerWidth,
          height: window.innerHeight
        }));
        const screenshot = await currentBrowserPage().screenshot({
          type: "jpeg",
          quality: 70,
          animations: "disabled",
          caret: "hide"
        });
        sendJson(response, 200, {
          image_base64: screenshot.toString("base64"),
          mime_type: "image/jpeg",
          width: viewport.width,
          height: viewport.height,
          url: currentPage().url()
        });
        return;
      }
      if (request.method !== "POST") {
        sendJson(response, 404, { error: "NOT_FOUND" });
        return;
      }
      const payload = await readJson(request);
      if (url.pathname === "/page/aria") {
        const selector = payload.selector === ":focus" ? ":focus" : "body";
        const locator = currentPage().locator(selector);
        const count = await locator.count();
        const snapshot = count === 1 ? await locator.ariaSnapshot({ timeout: 5_000 }) : null;
        sendJson(response, 200, { count, snapshot });
        return;
      }
      if (url.pathname === "/page/locator") {
        const locator = locate(payload);
        const count = await locator.count();
        sendJson(response, 200, {
          count,
          visible: count === 1 ? await locator.isVisible() : false,
          enabled: count === 1 ? await locator.isEnabled() : false,
          editable: count === 1 && ["textbox", "combobox"].includes(payload.role)
            ? await locator.isEditable()
            : false
        });
        return;
      }
      if (url.pathname === "/page/action") {
        const op = String(payload.op ?? "");
        let result = {};
        if (["focus", "fill", "press", "select", "set_checked", "scroll"].includes(op)) {
          const locator = locate(payload);
          if (await locator.count() !== 1) throw new Error("STRICT_LOCATOR_REQUIRED");
          if (op === "focus") await locator.focus({ timeout: 3_000 });
          if (op === "fill") await locator.fill(String(payload.value ?? ""), { timeout: 3_000 });
          if (op === "press") await locator.press(String(payload.key ?? ""), { timeout: 3_000 });
          if (op === "select") result.selected = await locator.selectOption({ label: String(payload.value ?? "") }, { timeout: 3_000 });
          if (op === "set_checked") await locator.setChecked(Boolean(payload.checked), { timeout: 3_000 });
          if (op === "scroll") await locator.scrollIntoViewIfNeeded({ timeout: 3_000 });
        } else if (op === "keyboard_press") {
          await currentKeyboard().press(String(payload.key ?? ""));
        } else if (op === "coordinate_click" || op === "coordinate_type") {
          const viewport = await currentPage().evaluate(() => ({
            width: window.innerWidth,
            height: window.innerHeight
          }));
          const x = Number(payload.x);
          const y = Number(payload.y);
          if (!Number.isInteger(x) || !Number.isInteger(y)) throw new Error("INVALID_COORDINATE");
          if (x < 0 || y < 0 || x >= viewport.width || y >= viewport.height) {
            throw new Error("COORDINATE_OUT_OF_VIEWPORT");
          }
          await currentBrowserPage().mouse.click(x, y);
          if (op === "coordinate_type") {
            const value = String(payload.value ?? "");
            if (value.length > 4_000) throw new Error("INPUT_TOO_LONG");
            await currentKeyboard().press(process.platform === "darwin" ? "Meta+A" : "Control+A");
            await currentKeyboard().type(value);
          }
        } else if (op === "coordinate_scroll") {
          const deltaY = Number(payload.delta_y);
          if (!Number.isInteger(deltaY) || deltaY === 0 || Math.abs(deltaY) > 1_000) {
            throw new Error("INVALID_SCROLL_DELTA");
          }
          await currentBrowserPage().mouse.wheel(0, deltaY);
        } else if (op === "goto") {
          await currentPage().goto(localUrl(String(payload.value ?? "")), { waitUntil: "domcontentloaded", timeout: 5_000 });
        } else if (op === "go_back") {
          const before = currentPage().url();
          if (typeof currentPage().goBack === "function") {
            await currentPage().goBack({ waitUntil: "domcontentloaded", timeout: 5_000 });
          } else {
            await currentPage().evaluate(() => window.history.back());
            await currentPage().waitForTimeout(300);
          }
          result.moved = currentPage().url() !== before;
        } else if (op === "wait") {
          await currentPage().waitForTimeout(Number(payload.duration_ms ?? 0));
        } else {
          throw new Error("UNSUPPORTED_BRIDGE_ACTION");
        }
        sendJson(response, 200, { success: true, url: currentPage().url(), ...result });
        return;
      }
      sendJson(response, 404, { error: "NOT_FOUND" });
    } catch (error) {
      sendJson(response, 422, { error: error instanceof Error ? error.message : "BRIDGE_ERROR" });
    }
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
  return {
    port,
    close: () => new Promise((resolve) => server.close(resolve))
  };
};
