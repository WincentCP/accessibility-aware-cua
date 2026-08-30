import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("research starts from one accessible action without identity or consent forms", async ({ page }) => {
  await page.goto("/researcher");
  await expect(page.getByRole("heading", { name: "Siap mulai?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mulai Penelitian" })).toBeVisible();
  await expect(page.getByLabel("Kode peserta")).toHaveCount(0);
  await expect(page.getByText("Periksa sistem", { exact: false })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("one click guides permissions without a blank popup and prepares task one", async ({ page }) => {
  await page.addInitScript(() => {
    class FakeStream {
      getAudioTracks() { return [{ stop() {} }]; }
      getVideoTracks() { return [{ stop() {}, addEventListener() {} }]; }
      getTracks() { return [...this.getAudioTracks(), ...this.getVideoTracks()]; }
    }
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => new FakeStream(),
        getDisplayMedia: async () => new FakeStream()
      }
    });
    Object.defineProperty(HTMLMediaElement.prototype, "srcObject", {
      configurable: true,
      get() { return null; },
      set() {}
    });

    class FakeMediaRecorder extends EventTarget {
      static isTypeSupported() { return true; }
      state = "inactive";
      mimeType = "video/webm";
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        this.dispatchEvent(new MessageEvent("dataavailable", { data: new Blob(["recording"], { type: "video/webm" }) }));
        this.dispatchEvent(new Event("stop"));
      }
    }
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeMediaRecorder });

    class FakeAudio {
      listeners = new Map<string, EventListener>();
      constructor(_source?: string) {}
      addEventListener(type: string, listener: EventListener) { this.listeners.set(type, listener); }
      play() {
        setTimeout(() => this.listeners.get("ended")?.(new Event("ended")), 0);
        return Promise.resolve();
      }
    }
    Object.defineProperty(window, "Audio", { configurable: true, value: FakeAudio });

    class FakeAudioNode {
      gain = { value: 0 };
      connect() { return this; }
      addEventListener() {}
    }
    class FakeAudioContext {
      sampleRate = 48_000;
      destination = new FakeAudioNode();
      createMediaStreamSource() { return new FakeAudioNode(); }
      createScriptProcessor() { return new FakeAudioNode(); }
      createGain() { return new FakeAudioNode(); }
    }
    Object.defineProperty(window, "AudioContext", { configurable: true, value: FakeAudioContext });

    class FakeWebSocket extends EventTarget {
      static OPEN = 1;
      readyState = 1;
      constructor(_url: string) {
        super();
        setTimeout(() => this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({ type: "ready" }) })), 0);
      }
      send() {}
      close() { this.dispatchEvent(new Event("close")); }
    }
    Object.defineProperty(window, "WebSocket", { configurable: true, value: FakeWebSocket });
  });

  await page.route("**/api/study/readiness", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ready: true, agent: { status: "ready" } })
  }));
  await page.route("**/api/voice/speech", (route) => route.fulfill({
    status: 200,
    contentType: "audio/wav",
    body: "fake-audio"
  }));

  await page.goto("/researcher");
  let popupOpened = false;
  page.on("popup", () => { popupOpened = true; });
  await page.getByRole("button", { name: "Mulai Penelitian" }).click();
  await expect(page.locator("#recording-state")).toHaveText("Rekaman aktif");
  await expect(page.locator("#task-state")).toContainText("Kegiatan 1 dari 4");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.taskUrl ?? ""))
    .toMatch(/study_session_id=/u);
  expect(popupOpened).toBe(false);
  await expect(page.getByLabel("Pratinjau kamera peserta")).toBeVisible();
  await expect(page.locator("canvas[hidden]")).toHaveCount(1);
});
