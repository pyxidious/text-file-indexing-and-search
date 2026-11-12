"""Acquisisce Cranfield oppure verifica lo snapshot locale in modalità offline."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.acquire import DEFAULT_CACHE, acquire


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    records = acquire(args.cache, offline=args.offline)
    print("Snapshot verificato:", {key: len(value) for key, value in records.items()})


if __name__ == "__main__":
    main()
