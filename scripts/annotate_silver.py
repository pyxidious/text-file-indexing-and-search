"""Pipeline silver separata: pianificazione, inferenza esplicita, validazione e report."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.silver.data import DEFAULT_CONFIG, DEFAULT_DATASET, DEFAULT_OUTPUT, prepare_study
from irhome.silver.evaluation import import_manual_review
from irhome.silver.report import make_report
from irhome.silver.runner import annotate, dry_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "dry-run", "annotate", "evaluate", "report", "import-review"):
        sub = commands.add_parser(name)
        sub.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
        sub.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        if name == "prepare":
            sub.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        if name in ("dry-run", "annotate"):
            sub.add_argument("--phase", choices=("pilot", "unjudged", "future", "all") if name == "dry-run"
                             else ("pilot", "unjudged", "future"), default="pilot")
            sub.add_argument("--max-requests", type=int, default=None)
        if name == "annotate":
            sub.add_argument("--retry-uncertain", action="store_true",
                             help="Ritenta richieste dal risultato incerto: possibile doppio addebito")
        if name == "import-review":
            sub.add_argument("csv", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        identity = prepare_study(args.dataset, args.output, args.config)
        result = {"prepared": True, "prompt_version": identity["settings"]["prompt_version"],
                  "model_id": identity["settings"]["model_id"], "output": str(args.output)}
    elif args.command == "dry-run":
        phases = ("pilot", "unjudged", "future") if args.phase == "all" else (args.phase,)
        result = {phase: dry_run(args.dataset, args.output, phase, args.max_requests) for phase in phases}
    elif args.command == "annotate":
        result = annotate(args.dataset, args.output, args.phase, args.max_requests, args.retry_uncertain)
    elif args.command == "import-review":
        result = import_manual_review(args.dataset, args.output, args.csv)
    else:
        report = make_report(args.dataset, args.output)
        result = {"annotations_really_executed": report["annotations_really_executed"],
                  "status": report["status"], "confusion_matrix": report["pilot_agreement"]["confusion_matrix"],
                  "report": str(args.output / "report.md")}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "annotate" and result.get("status") in (
            "not_executed_provider_unavailable", "stopped_provider_or_integrity_error"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
