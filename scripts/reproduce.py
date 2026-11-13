"""Verifica corpus, prepara la matrice semantica, esegue test e benchmark."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irhome.benchmark import benchmark
from irhome.dataset import analyze, verify_corpus
from irhome.engine import SearchEngine
from irhome.evaluation import evaluate
from irhome.semantic import prepare


def main():
    verify_corpus()
    stats = analyze()
    print(f"Corpus verificato: {stats['documents']} documenti; {stats['tokens']} token", flush=True)
    if not Path("evaluation/semantic/frozen.json").exists():
        prepare("corpus/documents")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], check=True)
    engine = SearchEngine.build("corpus/documents")
    engine.save("artifacts/homework/index.json")
    benchmark()
    if Path("evaluation/semantic/frozen.json").exists():
        evaluate()
    else:
        print("Ground truth semantica pendente: completare evaluation/semantic/annotations.csv e freeze. Nessuna metrica sul corpus calcolata.")


if __name__ == "__main__":
    main()
