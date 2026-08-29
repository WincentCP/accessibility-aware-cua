"""Tiny researcher-only Windows launcher; participant never sees this window."""

from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parents[1]
CREATE_NO_WINDOW = 0x08000000


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Mulai Pengujian CUA")
        self.geometry("520x260")
        self.minsize(460, 240)
        self.configure(bg="#f5f6fb")
        self.process: subprocess.Popen[str] | None = None

        tk.Label(self, text="Mulai Pengujian CUA", font=("Segoe UI", 20, "bold"), bg="#f5f6fb", fg="#243141").pack(anchor="w", padx=28, pady=(26, 4))
        tk.Label(self, text="Database, backend, browser, dan agent disiapkan otomatis.", font=("Segoe UI", 10), bg="#f5f6fb", fg="#526172").pack(anchor="w", padx=28, pady=(0, 20))
        self.research_button = self._button("Mulai Penelitian", self.start_research)
        self.status = tk.StringVar(value="Siap.")
        tk.Label(self, textvariable=self.status, wraplength=450, justify="left", font=("Segoe UI", 10), bg="#e3f0f3", fg="#254b5b", padx=14, pady=12).pack(fill="x", padx=28, pady=(18, 0))
        self.protocol("WM_DELETE_WINDOW", self.close_launcher)

    def _button(self, label: str, command: object, *, secondary: bool = False) -> tk.Button:
        button = tk.Button(self, text=label, command=command, font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2", bg="#e3f0f3" if secondary else "#315f73", fg="#254b5b" if secondary else "white", activebackground="#d5e8ec" if secondary else "#254b5b", activeforeground="#243141" if secondary else "white", padx=18, pady=10)
        button.pack(fill="x", padx=28, pady=5)
        return button

    def run_mode(self, check: bool) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Sesi aktif", "Satu sesi masih berjalan. Tutup browser sebelum memulai lagi.")
            return
        self.research_button.configure(state="disabled")
        self.status.set("Menyiapkan sistem. Browser akan terbuka otomatis.")

        def worker() -> None:
            args = ["node", "scripts/launch-test-agent.mjs", *(["--check"] if check else [])]
            log_path = ROOT / ".runtime" / "logs" / "research-launcher.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with log_path.open("ab") as output:
                    self.process = subprocess.Popen(
                        args,
                        cwd=ROOT,
                        creationflags=CREATE_NO_WINDOW,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                    )
                    code = self.process.wait()
                self.after(0, lambda: self.status.set("Pemeriksaan lulus." if check and code == 0 else "Sesi ditutup." if code == 0 else "Sistem belum siap. Buka log proyek untuk detail."))
            except OSError as exc:
                message = f"Launcher gagal: {exc}"
                self.after(0, lambda: self.status.set(message))
            finally:
                self.after(0, lambda: self.research_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def start_research(self) -> None:
        self.run_mode(False)

    def close_launcher(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.destroy()


if __name__ == "__main__":
    Launcher().mainloop()
