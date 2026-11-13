"""Verifica corpus, propone giudizi, esegue test e benchmark; rispetta la revisione."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.benchmark import benchmark
from irhome.dataset import analyze, verify_corpus
from irhome.engine import SearchEngine
from irhome.evaluation import evaluate
from irhome.ground_truth import propose


def main():
    verify_corpus()
    stats = analyze()
    print(f"Corpus verificato: {stats['documents']} documenti; {stats['tokens']} token", flush=True)
    if not Path("evaluation/frozen.json").exists():
        propose("corpus/documents")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], check=True)
    engine = SearchEngine.build("corpus/documents")
    engine.save("artifacts/homework/index.json")
    benchmark()
    if Path("evaluation/frozen.json").exists():
        evaluate()
    else:
        print("Ground truth proposta: completare review.csv e freeze. Nessuna metrica sul corpus calcolata.")


if __name__ == "__main__":
    main()
