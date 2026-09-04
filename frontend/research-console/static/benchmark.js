(() => {
  "use strict";

  const form = document.querySelector("[data-benchmark-form]");
  const status = document.querySelector("#task-status");
  const workspace = document.querySelector(".workspace");
  if (!form || !status || !workspace) return;

  form.addEventListener("submit", (event) => {
    if (!form.checkValidity()) return;
    const delay = Number.parseInt(form.dataset.delayMs || "0", 10);
    status.textContent = delay > 0
      ? `Aksi diterima. Pembaruan terkontrol berjalan sekitar ${delay} milidetik.`
      : "Aksi diterima. Memperbarui status task.";
    workspace.setAttribute("aria-busy", "true");
    const button = event.submitter;
    if (button) {
      button.setAttribute("aria-disabled", "true");
      button.textContent = "Memproses…";
    }
  });
})();
