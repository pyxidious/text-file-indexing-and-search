"""Metriche complete e @10, soltanto con ground truth validata e congelata."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", default="corpus/documents")
    parser.add_argument("--queries", default="evaluation/queries.csv")
    parser.add_argument("--ground-truth", default="evaluation")
    parser.add_argument("--output", default="artifacts/homework/results")
    args = parser.parse_args()
    try:
        evaluate(args.documents, args.queries, args.ground_truth, args.output)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
