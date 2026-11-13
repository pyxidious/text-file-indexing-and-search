"""Preparazione, annotazione e congelamento della ground truth semantica."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.semantic import prepare, annotate, freeze, checked_rows, progress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "annotate", "status", "freeze"))
    parser.add_argument("--documents", default="corpus/documents")
    parser.add_argument("--queries", default="evaluation/queries.csv")
    parser.add_argument("--output", default="evaluation/semantic")
    parser.add_argument("--metadata", default="corpus/metadata.csv")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--approval-note", default="")
    args = parser.parse_args()
    params = dict(documents=args.documents, queries=args.queries, output=args.output, metadata=args.metadata)
    try:
        if args.command == "freeze":
            print(freeze(**params, reviewer=args.reviewer, approval_note=args.approval_note)["status"])
        elif args.command == "annotate":
            annotate(**params)
        elif args.command == "status" and (Path(args.output) / "frozen.json").exists():
            from irhome.semantic import load_frozen
            load_frozen(**params)
            print("semantic_ground_truth_human_annotated (hash verificati)")
        else:
            entries, qs, _, _ = prepare(**params)
            rows = checked_rows(args.output, entries, qs)
            print(progress(rows, qs))
            for row in rows:
                doubtful = [q["query_id"] for q in qs if row[q["query_id"]] == "?"]
                if doubtful:
                    print(row["doc_id"], "dubbi:", ", ".join(doubtful))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
