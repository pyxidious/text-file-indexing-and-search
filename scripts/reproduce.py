"""Punto d'ingresso unico: ambiente, dati, indici, test, query e misure reali."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import ROOT
from irhome.experiment import evaluate_collections, prepare_collections, validate_config
from irhome.io import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "experiment.json")
    parser.add_argument("--output", type=Path, default=Path("artifacts/experiment"))
    args = parser.parse_args()
    config = read_json(args.config)
    validate_config(config)
    print(f"Ambiente verificato: Python {sys.version.split()[0]}; configurazione {config}", flush=True)
    samples = prepare_collections(args.output, config)
    # Il processo fallisce se un test non passa; nessuna metrica di successo inventata.
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=ROOT, check=True)
    evaluate_collections(args.output, config, samples)
    print(f"Riproduzione completata: {args.output / 'results'}", flush=True)


if __name__ == "__main__":
    main()
