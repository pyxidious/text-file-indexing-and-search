"""Protocollo LESSICALE storico; per la valutazione usare semantic_ground_truth.py."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.ground_truth import propose, freeze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("propose", "freeze"))
    parser.add_argument("--documents", type=Path, default=Path("corpus/documents"))
    parser.add_argument("--queries", type=Path, default=Path("evaluation/queries.csv"))
    parser.add_argument("--output", type=Path, default=Path("evaluation"))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--approval-note", default="")
    args = parser.parse_args()
    try:
        if args.command == "propose":
            report = propose(args.documents, args.queries, args.output)
            print(f"Proposte automatiche: {report['documents']} documenti, {report['checks']} verifiche")
            for qid, count in report["positives"].items():
                print(f"{qid}: {count} positivi proposti")
            print("Revisione umana ancora necessaria; metriche non calcolate.")
        else:
            freeze(args.documents, args.queries, args.output,
                   reviewer=args.reviewer, approval_note=args.approval_note)
            print("Ground truth validata e congelata prima della valutazione.")
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
