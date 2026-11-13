"""Misura esclusivamente la costruzione degli indici (100/200/tutti i file)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.benchmark import benchmark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", default="corpus/documents")
    parser.add_argument("--output", default="evaluation")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    benchmark(args.documents, args.output, args.repetitions)


if __name__ == "__main__":
    main()
