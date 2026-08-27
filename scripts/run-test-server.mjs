#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const localPython = process.platform === "win32"
  ? resolve(root, ".venv", "Scripts", "python.exe")
  : resolve(root, ".venv", "bin", "python");
const python = existsSync(localPython)
  ? localPython
  : process.platform === "win32" ? "python" : "python3";
const child = spawn(python, ["scripts/run_test_server.py"], {
  cwd: root,
  env: process.env,
  stdio: "inherit"
});

const stop = (signal) => {
  if (!child.killed) child.kill(signal);
};
process.once("SIGINT", () => stop("SIGINT"));
process.once("SIGTERM", () => stop("SIGTERM"));
child.once("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.once("exit", (code) => {
  process.exit(code ?? 1);
});
