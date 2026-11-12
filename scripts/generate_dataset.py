"""Genera documenti, metadati, query, qrels e manifest."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import generate_dataset, verify_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/manual/dataset"))
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate_dataset(args.output, args.count, args.seed)
    print(f"Generati {args.count} documenti. Manifest SHA-256: {verify_dataset(args.output)}")


if __name__ == "__main__":
    main()
