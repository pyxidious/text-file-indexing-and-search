"""Punto d'ingresso unico: ambiente, dati, indici, test, query e misure reali."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.dataset import ROOT
from irhome.acquire import DEFAULT_CACHE
from irhome.experiment import evaluate_collections, prepare_collections, validate_config
from irhome.io import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "experiment.json")
    parser.add_argument("--output", type=Path, default=Path("artifacts/cranfield-experiment"))
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true", help="Vieta acquisizioni; richiede snapshot locale")
    args = parser.parse_args()
    config = read_json(args.config)
    validate_config(config)
    print(f"Ambiente verificato: Python {sys.version.split()[0]}; configurazione {config}", flush=True)
    samples = prepare_collections(args.output, config, args.cache, args.offline)
    # Il processo fallisce se un test non passa; nessuna metrica di successo inventata.
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    test_env = dict(os.environ, IRHOME_TEST_CACHE=str(args.cache.resolve()))
    tested = subprocess.run(command, cwd=ROOT, env=test_env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(tested.stdout, flush=True)
    log = args.output / "results" / "tests.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(tested.stdout.encode("utf-8"))
    tested.check_returncode()
    evaluate_collections(args.output, config, samples)
    print(f"Riproduzione completata: {args.output / 'results'}", flush=True)


if __name__ == "__main__":
    main()
