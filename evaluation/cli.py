"""Command-line entry point for manifest validation, live runs, and reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from backend.agent.persistence import AuditRepository
from backend.api.config import ROOT, Settings
from evaluation.api_executor import ApiRunExecutor
from evaluation.config import EvaluationConfiguration
from evaluation.report import write_reports
from evaluation.runner import EvaluationRunner, load_manifest, validate_pilot_gate
from evaluation.storage import JsonResultStore, PostgresResultStore

MANIFESTS = {
    "pilot": ROOT / "benchmark/private/manifests/pilot_runs.json",
    "final": ROOT / "benchmark/private/manifests/final_runs.json",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cua-evaluate")
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="Validasi manifest dan pairing.")
    validate.add_argument("split", choices=sorted(MANIFESTS))
    run = subcommands.add_parser("run", help="Jalankan B0/B1/P secara live dan resumable.")
    run.add_argument("split", choices=sorted(MANIFESTS))
    run.add_argument("--config", action="append", choices=["B0", "B1", "P"], dest="configs")
    run.add_argument("--max-runs", type=int)
    run.add_argument("--json-store", type=Path)
    run.add_argument("--api-url", default="http://127.0.0.1:8000")
    report = subcommands.add_parser("report", help="Ekspor CSV/JSON dari hasil tersimpan.")
    report.add_argument("--json-store", type=Path)
    report.add_argument("--output", type=Path, default=ROOT / ".runtime/evaluation/report")
    return parser


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = _parser().parse_args()
    if args.command == "validate":
        runs = load_manifest(MANIFESTS[args.split])
        print(json.dumps({"valid": True, "split": args.split, "runs": len(runs)}))
        return
    settings = Settings.from_env()
    if getattr(args, "json_store", None):
        store = JsonResultStore(args.json_store)
    else:
        AuditRepository(settings.database_url).migrate()
        store = PostgresResultStore(settings.database_url)
    if args.command == "run":
        executor = ApiRunExecutor(
            api_url=args.api_url,
            bridge_url=settings.browser_bridge_url,
            app_secret=settings.app_secret,
            gemini_api_key=settings.gemini_api_key or "",
            planner_model=settings.planner_model,
            planner_fallback_model=settings.planner_fallback_model,
            gemini_max_retries=settings.gemini_max_retries,
        )
        if args.split == "final":
            if args.configs:
                raise SystemExit(
                    "Final run wajib mempertahankan urutan B0/B1/P dari manifest; --config tidak diizinkan."
                )
            validate_pilot_gate(
                store,
                load_manifest(MANIFESTS["pilot"]),
                executor=executor,
            )
        configurations = {
            EvaluationConfiguration(value) for value in (args.configs or ["B0", "B1", "P"])
        }
        runner = EvaluationRunner(
            executor=executor,
            store=store,
        )
        produced = runner.run(
            load_manifest(MANIFESTS[args.split]),
            configurations=configurations,
            max_runs=args.max_runs,
        )
        print(json.dumps({"executed_attempts": len(produced)}, ensure_ascii=False))
        return
    paths = write_reports(store.all_results(), args.output)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
