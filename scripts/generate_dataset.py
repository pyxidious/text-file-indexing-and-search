"""Prepara Cranfield in TXT da snapshot verificato (nome del comando conservato)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.acquire import DEFAULT_CACHE, DEFAULT_LOCK, acquire
from irhome.dataset import prepare_dataset, verify_dataset
from irhome.io import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cranfield-manual/dataset"))
    parser.add_argument("--count", type=int, default=1400, help="Prefisso numerico; benchmark IR solo su 1400")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    records = acquire(args.cache, offline=args.offline)
    prepare_dataset(args.output, records, args.count, read_json(DEFAULT_LOCK)["records_sha256"])
    print(f"Preparati {args.count} documenti. Manifest SHA-256: {verify_dataset(args.output)}")


if __name__ == "__main__":
    main()
