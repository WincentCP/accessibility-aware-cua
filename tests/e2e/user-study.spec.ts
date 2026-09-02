import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const installResearchBrowserFakes = async (
  page: Page,
  options: { permissionDelayMs?: number; audioAutoEnd?: boolean } = {}
) => {
  await page.addInitScript(({ permissionDelayMs, audioAutoEnd }) => {
    class FakeStream {
      getAudioTracks() { return [{ stop() {} }]; }
      getVideoTracks() { return [{ stop() {}, addEventListener() {} }]; }
      getTracks() { return [...this.getAudioTracks(), ...this.getVideoTracks()]; }
    }
    const createStream = async () => {
      if (permissionDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, permissionDelayMs));
      }
      return new FakeStream();
    };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: createStream,
        getDisplayMedia: createStream
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
        if (audioAutoEnd) setTimeout(() => this.listeners.get("ended")?.(new Event("ended")), 0);
        return Promise.resolve();
      }
      pause() {}
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
  }, {
    permissionDelayMs: options.permissionDelayMs ?? 0,
    audioAutoEnd: options.audioAutoEnd ?? true
  });
};

test("research starts from one accessible action without a visual identity form", async ({ page }) => {
  await page.goto("/researcher");
  await expect(page.getByRole("heading", { name: "Sesi Kegiatan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mulai Penelitian" })).toBeVisible();
  await expect(page.getByText("Tekan mulai. Setelah itu, cukup dengarkan dan bicara.")).toBeVisible();
  await expect(page.getByLabel("Kode peserta")).toHaveCount(0);
  await expect(page.getByText("Periksa sistem", { exact: false })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("one click guides permissions in one tab and enters voice onboarding", async ({ page }) => {
  test.setTimeout(60_000);
  await installResearchBrowserFakes(page);

  await page.route("**/api/study/readiness", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ready: true, agent: { status: "ready" } })
  }));
  let permissionGuideRequests = 0;
  await page.route("**/api/voice/speech", (route) => {
    permissionGuideRequests += 1;
    return route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({ detail: "TTS unavailable" })
    });
  });

  await page.goto("/researcher");
  let popupOpened = false;
  page.on("popup", () => { popupOpened = true; });
  await page.getByRole("button", { name: "Mulai Penelitian" }).click();
  await expect(page.locator("#microphone-permission-state")).toHaveText("Siap");
  await expect(page.locator("#camera-permission-state")).toHaveText("Siap");
  await expect(page.locator("#screen-permission-state")).toHaveText("Siap");
  await expect(page.locator("#recording-state")).toHaveText("Rekaman aktif");
  await expect(page.locator("#task-state")).toContainText("Kegiatan 1 dari 4");
  await expect(page.locator("#session-message")).toContainText("berkenalan");
  expect(permissionGuideRequests).toBe(0);
  await expect(page.locator("#study-task-frame")).toBeHidden();
  expect(popupOpened).toBe(false);
  await expect(page.getByLabel("Pratinjau kamera peserta")).toBeVisible();
  await expect(page.locator("canvas[hidden]")).toHaveCount(1);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("an active permission guide stops as soon as device sharing is ready", async ({ page }) => {
  await installResearchBrowserFakes(page, { permissionDelayMs: 800, audioAutoEnd: false });
  await page.route("**/api/study/readiness", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ready: true, agent: { status: "ready" } })
  }));
  let permissionGuideRequests = 0;
  await page.route("**/api/voice/speech", (route) => {
    permissionGuideRequests += 1;
    return route.fulfill({ status: 200, contentType: "audio/wav", body: "fake-audio" });
  });

  await page.goto("/researcher");
  await page.getByRole("button", { name: "Mulai Penelitian" }).click();

  await expect(page.locator("#recording-state")).toHaveText("Rekaman aktif");
  await expect(page.locator("#session-message")).toContainText("berkenalan");
  await expect(page.locator("#session-error")).toBeHidden();
  expect(permissionGuideRequests).toBe(1);
});

test("a silent voice coordinator is retried with spoken recovery and then fails closed", async ({ page }) => {
  test.setTimeout(60_000);
  await installResearchBrowserFakes(page);
  await page.route("**/api/study/readiness", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ready: true, agent: { status: "ready" } })
  }));
  let spokenRecoveryRequests = 0;
  await page.route("**/api/voice/speech", (route) => {
    spokenRecoveryRequests += 1;
    return route.fulfill({ status: 200, contentType: "audio/wav", body: "fake-audio" });
  });

  await page.goto("/researcher");
  await page.getByRole("button", { name: "Mulai Penelitian" }).click();
  await expect(page.locator("#recording-state")).toHaveText("Rekaman aktif");

  await page.evaluate(() => window.dispatchEvent(new CustomEvent("a11y-cua:coordinator-error")));
  await expect(page.locator("#session-message")).toContainText("disambungkan kembali");
  await expect.poll(() => spokenRecoveryRequests).toBe(1);

  await page.evaluate(() => window.dispatchEvent(new CustomEvent("a11y-cua:coordinator-error")));
  await expect.poll(() => spokenRecoveryRequests).toBe(2);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("a11y-cua:coordinator-error")));

  await expect(page.locator("html")).toHaveAttribute("data-research-state", "error");
  await expect(page.locator("#session-error")).toContainText("setelah tiga percobaan");
  await expect.poll(() => spokenRecoveryRequests).toBe(3);
});

test("active participant view keeps the guide compact and the task canvas dominant", async ({ page, request }) => {
  test.setTimeout(90_000);
  const created = await request.post("/api/study/automatic", { data: { condition_id: "C0" } });
  const study = await created.json();
  const studyId = study.study_session_id as string;
  await request.post(`/api/study/sessions/${studyId}/automatic-readiness`, {
    data: { checks: { backend: true, agent: true, microphone: true, camera: true, screen: true, audio: true } }
  });
  await request.post(`/api/study/sessions/${studyId}/participant-profile`, {
    data: { name: "Raka", name_spelling: "R A K A", participant_class: "Kelas 8", age: 14 }
  });
  const taskResponse = await request.post(`/api/study/sessions/${studyId}/tasks/start`);
  const task = await taskResponse.json();

  await page.goto("/researcher");
  await page.evaluate((taskUrl) => {
    document.querySelector<HTMLElement>("#research-start")!.hidden = true;
    document.querySelector<HTMLElement>("#live-session")!.hidden = false;
    document.documentElement.dataset.researchState = "listening";
    document.documentElement.dataset.taskUrl = taskUrl;
    const frame = document.querySelector<HTMLIFrameElement>("#study-task-frame")!;
    frame.hidden = false;
    frame.src = taskUrl;
  }, task.start_url as string);

  await expect(page.locator("#study-task-frame")).toBeVisible();
  await expect(page.frameLocator("#study-task-frame").locator("body")).toHaveClass(/study-mode/);
  await expect(page.frameLocator("#study-task-frame").getByText("Kontrol eksperimen")).toHaveCount(0);
  const layout = await page.evaluate(() => {
    const guide = document.querySelector<HTMLElement>(".session-guide")!.getBoundingClientRect();
    const workspace = document.querySelector<HTMLElement>(".study-workspace")!.getBoundingClientRect();
    return {
      guideHeight: guide.height,
      workspaceHeight: workspace.height,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth
    };
  });
  expect(layout.guideHeight).toBeLessThan(150);
  expect(layout.workspaceHeight).toBeGreaterThan(450);
  expect(layout.overflow).toBe(false);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileLayout = await page.evaluate(() => ({
    guideHeight: document.querySelector<HTMLElement>(".session-guide")!.getBoundingClientRect().height,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth
  }));
  const taskFrame = page.frames().find((frame) => frame.url().includes(`study_session_id=${studyId}`));
  const taskOverflow = await taskFrame!.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(mobileLayout.guideHeight).toBeLessThan(260);
  expect(mobileLayout.overflow).toBe(false);
  expect(taskOverflow).toBe(false);
});
