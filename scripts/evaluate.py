"""Benchmark completo senza test (per test e benchmark insieme usare reproduce.py)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import ROOT
from irhome.experiment import evaluate_collections, prepare_collections
from irhome.io import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "experiment.json")
    parser.add_argument("--output", type=Path, default=Path("artifacts/experiment"))
    args = parser.parse_args()
    config = read_json(args.config)
    samples = prepare_collections(args.output, config)
    evaluate_collections(args.output, config, samples)
    print(f"Risultati esportati in {args.output / 'results'}")


if __name__ == "__main__":
    main()
